from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .catalog import GameCatalogEntry, build_catalog, resolve_game_entry
from .client import PuzzleScriptClient
from .scorecards import ScorecardStore


ACTION_IDS = {
    "RESET": 0,
    "ACTION1": 1,
    "ACTION2": 2,
    "ACTION3": 3,
    "ACTION4": 4,
    "ACTION5": 5,
    "ACTION7": 7,
}


def _arc_state(state: str) -> str:
    normalized = (state or "").upper()
    if normalized == "WIN":
        return "WIN"
    if normalized == "GAME_OVER":
        return "GAME_OVER"
    if normalized == "NOT_STARTED":
        return "NOT_STARTED"
    return "NOT_FINISHED"


def _available_actions(payload: dict[str, Any]) -> list[int]:
    mapped_actions = []
    for action_name in payload.get("available_actions") or []:
        action_id = ACTION_IDS.get(str(action_name).upper())
        if action_id is None or action_id == 0:
            continue
        mapped_actions.append(action_id)
    return mapped_actions or [1, 2, 3, 4, 5]


@dataclass
class SessionBinding:
    guid: str
    card_id: str
    game_id: str
    source_name: str
    session_id: str
    win_levels: int


class OpenScorecardRequest(BaseModel):
    source_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    opaque: dict[str, Any] | None = None


class CloseScorecardRequest(BaseModel):
    card_id: str


class ResetRequest(BaseModel):
    game_id: str
    card_id: str
    guid: str | None = None


class ActionRequest(BaseModel):
    game_id: str
    guid: str
    reasoning: Any | None = None
    x: int | None = None
    y: int | None = None


def _games_root() -> Path:
    return Path(__file__).resolve().parents[2] / "games"


def _frame_response(
    payload: dict[str, Any], binding: SessionBinding, action_name: str
) -> dict[str, Any]:
    return {
        "game_id": binding.game_id,
        "guid": binding.guid,
        "frame": payload.get("frame", []),
        "state": _arc_state(payload.get("state", "PLAYING")),
        "levels_completed": int(payload.get("levels_completed", 0)),
        "win_levels": binding.win_levels,
        "action_input": {"id": ACTION_IDS[action_name], "data": {}},
        "available_actions": _available_actions(payload),
    }


def create_app(
    *,
    catalog: list[GameCatalogEntry] | None = None,
    puzzlescript_client: PuzzleScriptClient | None = None,
) -> FastAPI:
    game_catalog = catalog or build_catalog(_games_root())
    client = puzzlescript_client or PuzzleScriptClient()
    scorecards = ScorecardStore()
    sessions_by_guid: dict[str, SessionBinding] = {}

    app = FastAPI(
        title="PuzzleScript ARC Service",
        description="ARC-compatible PuzzleScript backend",
        version="1.0.0",
    )

    @app.get("/api/games")
    def games() -> list[dict[str, str]]:
        return [
            {"game_id": entry.game_id, "title": entry.title} for entry in game_catalog
        ]

    @app.get("/api/games/{game_id}")
    def game_info(game_id: str) -> dict[str, Any]:
        try:
            entry = resolve_game_entry(game_catalog, game_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Game not found") from exc
        return {"game_id": entry.game_id, "title": entry.title}

    @app.post("/api/scorecard/open")
    def open_scorecard(request: OpenScorecardRequest | None = None) -> dict[str, str]:
        payload = request or OpenScorecardRequest()
        card = scorecards.open(
            tags=payload.tags, source_url=payload.source_url, opaque=payload.opaque
        )
        return {"card_id": card.card_id}

    @app.get("/api/scorecard/{card_id}")
    def get_scorecard(card_id: str) -> dict[str, Any]:
        try:
            return scorecards.get(card_id).to_summary()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Scorecard not found") from exc

    @app.post("/api/scorecard/close")
    def close_scorecard(request: CloseScorecardRequest) -> dict[str, Any]:
        try:
            return scorecards.close(request.card_id).to_summary()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Scorecard not found") from exc

    @app.post("/api/cmd/RESET")
    def reset_command(request: ResetRequest) -> dict[str, Any]:
        try:
            scorecards.require_open(request.card_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Scorecard not found") from exc

        entry = resolve_game_entry(game_catalog, request.game_id)
        if request.guid:
            binding = sessions_by_guid.get(request.guid)
            if not binding:
                raise HTTPException(status_code=404, detail="Session guid not found")
            if binding.card_id != request.card_id:
                raise HTTPException(status_code=400, detail="card_id mismatch")
            if binding.game_id != entry.game_id:
                raise HTTPException(status_code=400, detail="game_id mismatch")
            payload = client.reset_session(binding.session_id)
            scorecards.update_run(
                request.guid,
                levels_completed=int(payload.get("levels_completed", 0)),
                state=_arc_state(payload.get("state", "PLAYING")),
                increment_resets=1,
            )
            return _frame_response(payload, binding, "RESET")

        payload = client.start_game(entry.source_name)
        session_id = payload.get("sessionId")
        if not session_id:
            raise HTTPException(
                status_code=502, detail="PuzzleScript server did not return sessionId"
            )

        guid = str(uuid4())
        binding = SessionBinding(
            guid=guid,
            card_id=request.card_id,
            game_id=entry.game_id,
            source_name=entry.source_name,
            session_id=str(session_id),
            win_levels=int(payload.get("win_levels", 1)),
        )
        sessions_by_guid[guid] = binding
        scorecards.register_run(
            request.card_id,
            guid=guid,
            game_id=entry.game_id,
            session_id=binding.session_id,
            win_levels=binding.win_levels,
            levels_completed=int(payload.get("levels_completed", 0)),
            state=_arc_state(payload.get("state", "PLAYING")),
        )
        return _frame_response(payload, binding, "RESET")

    @app.post("/api/cmd/{action_name}")
    def action_command(action_name: str, request: ActionRequest) -> dict[str, Any]:
        action = action_name.upper()
        if action == "ACTION6":
            raise HTTPException(
                status_code=400, detail="ACTION6 is not supported by PuzzleScript"
            )
        if action not in {
            "ACTION1",
            "ACTION2",
            "ACTION3",
            "ACTION4",
            "ACTION5",
            "ACTION7",
        }:
            raise HTTPException(
                status_code=400, detail=f"Unsupported action '{action}'"
            )

        binding = sessions_by_guid.get(request.guid)
        if not binding:
            raise HTTPException(status_code=404, detail="Session guid not found")
        try:
            scorecards.require_open_for_guid(request.guid)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Scorecard not found") from exc
        if binding.game_id != resolve_game_entry(game_catalog, request.game_id).game_id:
            raise HTTPException(status_code=400, detail="game_id mismatch")

        payload = client.apply_action(binding.session_id, action)
        scorecards.update_run(
            request.guid,
            levels_completed=int(payload.get("levels_completed", 0)),
            state=_arc_state(payload.get("state", "PLAYING")),
            increment_actions=1,
        )
        return _frame_response(payload, binding, action)

    return app


app = create_app()
