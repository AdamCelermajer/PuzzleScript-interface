import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


PUZZLESCRIPT_SERVER_URL = os.getenv("PUZZLESCRIPT_SERVER_URL", "http://localhost:3000").rstrip("/")
# 7 (RESET) is intentionally excluded — agents must call /cmd/RESET, not /cmd/ACTION7
ARC_AVAILABLE_ACTIONS = [1, 2, 3, 4, 5]
ACTION_TO_ID = {
    "ACTION1": 1,
    "ACTION2": 2,
    "ACTION3": 3,
    "ACTION4": 4,
    "ACTION5": 5,
    "RESET": 7,
}


@dataclass
class SessionBinding:
    session_id: str
    game_id: str
    card_id: str
    win_levels: int
    legend: dict[int, str]


class ResetRequest(BaseModel):
    game_id: str
    card_id: str
    guid: str | None = None


class CommandRequest(BaseModel):
    game_id: str
    guid: str
    data: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(
    title="PuzzleScript ARC-AGI-3 Endpoint",
    description="ARC-compatible REST surface backed by PuzzleScript server.js",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scorecards: set[str] = set()
sessions_by_guid: dict[str, SessionBinding] = {}


def _http_json(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{PUZZLESCRIPT_SERVER_URL}{path}"
    if method.upper() == "GET":
        response = requests.request(method=method, url=url, params=payload, timeout=30)
    else:
        response = requests.request(method=method, url=url, json=payload, timeout=30)
    if response.status_code >= 400:
        detail = response.text
        try:
            err_data = response.json()
            if isinstance(err_data, dict):
                detail = str(err_data.get("error", detail))
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid JSON from PuzzleScript server: {exc}") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="PuzzleScript server returned unexpected response shape")
    return data


def _normalize_legend(raw: dict | None) -> dict[int, str]:
    legend: dict[int, str] = {}
    for key, value in (raw or {}).items():
        if str(key).lstrip("-").isdigit():
            legend[int(key)] = str(value)
    return legend


def _arc_state(legacy_state: str) -> str:
    state = (legacy_state or "").upper()
    if state == "WIN":
        return "WIN"
    if state == "GAME_OVER":
        return "GAME_OVER"
    return "NOT_FINISHED"


def _repo_games() -> list[dict[str, str]]:
    games_dir = Path(__file__).resolve().parents[1] / "games"
    if not games_dir.exists():
        return []

    games: list[dict[str, str]] = []
    for file_path in sorted(games_dir.glob("*.txt")):
        game_id = file_path.stem
        games.append({"game_id": game_id, "title": game_id})
    return games


def _base_arc_response(
    frame: list[list[list[int]]],
    state: str,
    binding: SessionBinding,
    guid: str,
    levels_completed: int,
    action_id: int,
) -> dict[str, Any]:
    return {
        "frame": frame,
        "state": state,
        "levels_completed": levels_completed,
        "game_id": binding.game_id,
        "win_levels": binding.win_levels,
        "guid": guid,
        "available_actions": ARC_AVAILABLE_ACTIONS,
        "action_input": {"id": action_id, "data": {}},
        "legend": binding.legend,
    }


def _ensure_scorecard(card_id: str) -> None:
    if card_id not in scorecards:
        raise HTTPException(status_code=400, detail="Missing or invalid card_id")


def _ensure_binding(guid: str, game_id: str, card_id: str | None = None) -> SessionBinding:
    binding = sessions_by_guid.get(guid)
    if not binding:
        raise HTTPException(status_code=404, detail="Session guid not found")
    if binding.game_id != game_id:
        raise HTTPException(status_code=400, detail=f"game_id mismatch: expected {binding.game_id}")
    if card_id is not None and binding.card_id != card_id:
        raise HTTPException(status_code=403, detail="card_id does not match the session that opened this guid")
    return binding


@app.get("/games")
def games() -> list[dict[str, str]]:
    return _repo_games()


@app.post("/scorecard/open")
def scorecard_open() -> dict[str, str]:
    card_id = f"card_{uuid.uuid4().hex[:12]}"
    scorecards.add(card_id)
    return {"card_id": card_id}


@app.post("/cmd/RESET")
def cmd_reset(request: ResetRequest) -> dict[str, Any]:
    _ensure_scorecard(request.card_id)

    if request.guid:
        binding = _ensure_binding(request.guid, request.game_id, request.card_id)
        reset = _http_json("POST", "/action", {"sessionId": binding.session_id, "action": "RESET"})
        return _base_arc_response(
            frame=reset.get("frame", []),
            state=_arc_state(reset.get("state", "PLAYING")),
            binding=binding,
            guid=request.guid,
            levels_completed=reset.get("levels_completed", 0),
            action_id=7,
        )

    init = _http_json("POST", "/init", {"gameName": request.game_id})
    session_id = init.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=502, detail="PuzzleScript server did not return sessionId")

    binding = SessionBinding(
        session_id=str(session_id),
        game_id=request.game_id,
        card_id=request.card_id,
        win_levels=int(init.get("win_levels", 1)),
        legend=_normalize_legend(init.get("legend")),
    )
    guid = f"guid_{uuid.uuid4().hex[:12]}"
    sessions_by_guid[guid] = binding

    return _base_arc_response(
        frame=init.get("frame", []),
        state=_arc_state(init.get("state", "PLAYING")),
        binding=binding,
        guid=guid,
        levels_completed=init.get("levels_completed", 0),
        action_id=7,
    )


@app.post("/cmd/{action_name}")
def cmd_action(action_name: str, request: CommandRequest) -> dict[str, Any]:
    action = action_name.upper()
    if action == "RESET":
        raise HTTPException(status_code=405, detail="Use /cmd/RESET for reset operations")
    if action == "ACTION6":
        raise HTTPException(status_code=400, detail="ACTION6 is not supported by PuzzleScript adapter")
    if action not in ACTION_TO_ID:
        raise HTTPException(status_code=400, detail=f"Unsupported action '{action}'")

    binding = _ensure_binding(request.guid, request.game_id)
    result = _http_json("POST", "/action", {"sessionId": binding.session_id, "action": action})

    return _base_arc_response(
        frame=result.get("frame", []),
        state=_arc_state(result.get("state", "PLAYING")),
        binding=binding,
        guid=request.guid,
        levels_completed=result.get("levels_completed", 0),
        action_id=ACTION_TO_ID[action],
    )


@app.get("/observe")
def observe(guid: str = Query(...)) -> dict[str, Any]:
    binding = sessions_by_guid.get(guid)
    if not binding:
        raise HTTPException(status_code=404, detail="Session guid not found")

    obs = _http_json("GET", "/observe", {"sessionId": binding.session_id})
    # Prefer live legend from server — server can add new tile mappings at runtime
    live_legend = _normalize_legend(obs.get("legend")) or binding.legend
    return {
        "frame": obs.get("frame", []),
        "state": _arc_state(obs.get("state", "PLAYING")),
        "levels_completed": obs.get("levels_completed", 0),
        "game_id": binding.game_id,
        "win_levels": binding.win_levels,
        "guid": guid,
        "available_actions": ARC_AVAILABLE_ACTIONS,
        "legend": live_legend,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ARC_PROXY_PORT", "8000")))
