"""Benchmark game metadata, live solve rates and manual play (contract section 4).

Replaces the Vite-only ``website/game-library-server.mjs`` routes. Game metadata
lives in ``benchmark/games.json`` (built by ``scripts/build_game_metadata.py``);
solve rates are computed from the run catalog on request and never stored.
Script source is never returned: it is the answer key for agents.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Literal

import requests
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from workbench.catalog import ROOT, read_json, snapshot

GAMES_JSON = Path("benchmark/games.json")
GAME_ID_RE = re.compile(r"^ps_[a-z0-9_]+-v\d+$")
PLAY_ACTIONS = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7", "RESET"}
MAX_PLAY_SESSIONS = 24
PLAY_IDLE_SECONDS = 30 * 60
MEASURED_TTL_SECONDS = 30


class TagSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mechanics: list[str] = Field(default_factory=list, max_length=40)
    properties: list[str] = Field(default_factory=list, max_length=40)


class BenchmarkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier: Literal["easy", "medium", "hard"] | None = None
    tags: TagSet | None = None
    notes: str | None = Field(default=None, max_length=16_000)
    summary: str | None = Field(default=None, max_length=300)


class PlayStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: int | None = Field(default=None, ge=0, le=500)


class RuleEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0)
    before: str
    value: str = Field(min_length=1, max_length=16_000)


def _write_json_atomic(path: Path, value: Any, newline: str = "\n") -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    handle, temp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline=newline) as stream:
            stream.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _entries(path: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(path) as listing:
            return sorted(listing, key=lambda e: e.name)
    except OSError:
        return []


def _check_id(game_id: str) -> str:
    if not GAME_ID_RE.match(game_id or ""):
        raise HTTPException(404, "Unknown benchmark game")
    return game_id


def measured_by_game(runs: list[dict]) -> dict[str, dict]:
    """Aggregate discovered run directories (queued children without artifacts are
    not runs yet). AVO fitness is levels completed by the fresh solver."""
    result: dict[str, dict] = {}
    for run in runs:
        game_id = run.get("game_id")
        if not game_id or "has_result" not in run:
            continue
        harness = run.get("harness") or run.get("agent_backend") or "unknown"
        levels = run.get("best_fitness") if run.get("kind") == "avo" else run.get("levels")
        levels = int(levels) if isinstance(levels, (int, float)) and not isinstance(levels, bool) else None
        game = result.setdefault(game_id, {"runs": 0, "solved_runs": 0, "best_levels": None, "by_harness": {}})
        for bucket in (game, game["by_harness"].setdefault(harness, {"runs": 0, "solved_runs": 0, "best_levels": None})):
            bucket["runs"] += 1
            bucket["solved_runs"] += run.get("solved") is True
            if levels is not None and (bucket["best_levels"] is None or levels > bucket["best_levels"]):
                bucket["best_levels"] = levels
    return result


def _empty_measured() -> dict:
    return {"runs": 0, "solved_runs": 0, "best_levels": None, "by_harness": {}}


def create_router(root: Path = ROOT, backend_url: str | None = None,
                  backend_post: Callable[[str, dict], dict] | None = None,
                  run_snapshot: Callable[[], dict] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/workbench")
    games_path = root / GAMES_JSON
    write_lock = threading.Lock()
    measured_lock = threading.Lock()
    measured_cache: dict[str, Any] = {}
    sessions: dict[str, dict] = {}
    sessions_lock = threading.Lock()
    base_url = (backend_url or os.environ.get("BENCHMARK_PLAY_BACKEND_URL")
                or f"http://localhost:{os.environ.get('ARC_PROXY_PORT', '8000')}").rstrip("/")

    def post(path: str, body: dict) -> dict:
        if backend_post:
            return backend_post(path, body)
        try:
            response = requests.post(base_url + path, json=body, timeout=30)
        except requests.RequestException as error:
            raise HTTPException(503, f"PuzzleScript ARC service unavailable at {base_url}: {error}") from error
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text[:300]
            raise HTTPException(502 if response.status_code >= 500 else response.status_code,
                                f"ARC service: {detail}")
        return response.json()

    def load() -> dict:
        data = read_json(games_path)
        if data.get("schema") != "games-v1":
            raise HTTPException(503, "benchmark/games.json is missing; run scripts.build_game_metadata")
        return data

    def refresh_measured() -> None:
        try:
            data = run_snapshot() if run_snapshot else snapshot(root, containers={})
            measured_cache.update(at=time.monotonic(), checked_at=data.get("checked_at", time.time()),
                                  runs=data.get("runs", []), warnings=data.get("warnings", []),
                                  by_game=measured_by_game(data.get("runs", [])))
        finally:
            measured_lock.release()

    def measured() -> tuple[dict, list[str], float]:
        """Stale-while-revalidate: the run catalog scan takes seconds, so only the
        first request waits; later ones get the previous aggregate at once."""
        if "by_game" not in measured_cache:
            measured_lock.acquire()
            if "by_game" in measured_cache:
                measured_lock.release()
            else:
                refresh_measured()
        elif (time.monotonic() - measured_cache["at"] > MEASURED_TTL_SECONDS
              and measured_lock.acquire(blocking=False)):
            threading.Thread(target=refresh_measured, daemon=True).start()
        return measured_cache["by_game"], measured_cache["warnings"], measured_cache["checked_at"]

    def public(game_id: str, entry: dict, by_game: dict) -> dict:
        return {"game_id": game_id, **entry, "measured": by_game.get(game_id) or _empty_measured()}

    @router.get("/benchmarks")
    def list_benchmarks(tier: str | None = None, tag: list[str] = Query(default=[]),
                        collection: str | None = None, status: str | None = None, q: str | None = None):
        data = load()
        by_game, warnings, checked_at = measured()
        needle = (q or "").strip().casefold()
        rows = []
        for game_id, entry in data["games"].items():
            if tier and (entry.get("tier") or "none") != tier.lower().replace("null", "none"):
                continue
            tags = set((entry.get("tags") or {}).get("mechanics", [])) | set((entry.get("tags") or {}).get("properties", []))
            if any(t not in tags for t in tag):
                continue
            if collection and collection not in entry.get("collections", []):
                continue
            if status and entry.get("status") != status:
                continue
            if needle and needle not in " ".join([game_id, entry.get("title", ""), entry.get("author", ""),
                                                  entry.get("summary", ""), entry.get("notes", ""), *tags]).casefold():
                continue
            rows.append(public(game_id, entry, by_game))
        return {"schema": data["schema"], "tag_vocabulary": data.get("tag_vocabulary", {}),
                "tag_definitions": data.get("tag_definitions", {}), "count": len(rows),
                "games": rows, "measured_at": checked_at, "warnings": warnings}

    def bfs_searches(game_id: str) -> list[dict]:
        out = []
        base = root / "experiement/bfs_solver"
        for entry in _entries(base):
            if not entry.is_file() or not re.search(r"(?:^results|_results).*\.json$", entry.name):
                continue
            data = read_json(Path(entry.path))
            for row in data.get("results") or []:
                if row.get("gameId") == game_id:
                    out.append({"source": f"experiement/bfs_solver/{entry.name}", "date": data.get("generatedAt"),
                                "solver": data.get("solver") or "BFS search", "level": row.get("levelIndex"),
                                "status": row.get("status"), "solved": row.get("solved"),
                                "depth": row.get("solutionDepth"), "expanded_states": row.get("expandedStates"),
                                "total_ms": row.get("totalMs")})
        return out

    def rule_archives(game_id: str) -> list[dict]:
        records = []

        def visit(path: Path, label: str, depth: int):
            files = _entries(path)
            names = {f.name for f in files if f.is_file()}
            if names & {"rules.json", "natural_rules.json"}:
                config = read_json(path / "run_config.json")
                def optional(name):
                    try:
                        return json.loads((path / name).read_text(encoding="utf-8-sig"))
                    except (OSError, ValueError):
                        return None
                records.append({"id": label, "model": config.get("model"),
                                "natural": optional("natural_rules.json"), "rules": optional("rules.json")})
            if depth:
                for f in files:
                    if f.is_dir() and not f.is_symlink():
                        visit(Path(f.path), f"{label}/{f.name}", depth - 1)

        visit(root / "client/rules" / game_id, f"client/rules/{game_id}", 3)
        return records

    def goal_studies(game_id: str) -> list[dict]:
        studies, published_id = [], None
        app_data = root / "studies/goal_recognition/website/app-data.js"
        try:
            text = app_data.read_text(encoding="utf-8-sig")
            published = json.loads(re.sub(r";\s*$", "", re.sub(r"^\s*window\.GOAL_RECOGNITION_RESULTS\s*=\s*", "", text)))
            published_id = published.get("run_id")
            game = next((g for g in published.get("games", []) if g.get("game_id") == game_id), None)
            if game:
                studies.append({"id": published_id, "source": "studies/goal_recognition/website/app-data.js",
                                "answers": len(game.get("llm_answers") or []),
                                "human_answers": len(game.get("human_answers") or []),
                                "screenshot": "/experiments/goal-recognition/" + game["screenshot"] if game.get("screenshot") else None})
        except (OSError, ValueError):
            pass
        base = root / "studies/goal_recognition/experiment/artifacts"
        for entry in _entries(base):
            if not entry.is_dir() or entry.name == published_id:
                continue
            path = Path(entry.path) / "predictions.jsonl"
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            count = 0
            for line in lines:
                try:
                    count += json.loads(line).get("game_id") == game_id
                except (ValueError, AttributeError):
                    pass
            if count:
                studies.append({"id": entry.name, "source": path.relative_to(root).as_posix(), "answers": count})
        return studies

    def selection_rules(game_id: str) -> list[str]:
        selection = read_json(root / "output/game-selection-20/selection.json")
        game = next((g for g in selection.get("games", []) if g.get("id") == game_id), None)
        return list(game.get("rules") or []) if game else []

    def level_annotations(game_id: str) -> dict:
        detail = read_json(root / "output/game-selection-20/level-annotation-detail.json")
        levels = [level for level in detail.get("levels", []) if level.get("game_id") == game_id]
        return {"methodology": detail.get("methodology"), "levels": levels} if levels else {}

    @router.get("/benchmarks/{game_id}")
    def benchmark_detail(game_id: str):
        data = load()
        entry = data["games"].get(_check_id(game_id))
        if entry is None:
            raise HTTPException(404, "Unknown benchmark game")
        by_game, warnings, checked_at = measured()
        try:
            readme = (root / "puzzlescript_interface/games" / game_id / "readme.txt").read_text(encoding="utf-8", errors="replace")
        except OSError:
            readme = None
        reference = read_json(root / "benchmark/games" / game_id / "game.json")
        runs = [{k: run.get(k) for k in ("id", "kind", "agent_backend", "harness", "model", "condition", "status",
                                        "solved", "levels", "best_fitness", "recorded_win_levels", "modified", "href")}
                for run in measured_cache.get("runs", []) if run.get("game_id") == game_id and "has_result" in run]
        return {**public(game_id, entry, by_game), "measured_at": checked_at, "warnings": warnings,
                "tag_definitions": data.get("tag_definitions", {}),
                "readme": readme, "runs": runs, "bfs_searches": bfs_searches(game_id),
                "reference": {"artifact_status": reference.get("artifact_status"),
                              "levels": [{"level": a.get("level_index"), "solution_actions": a.get("solution_actions"),
                                          "replay_verified": a.get("replay_verified")}
                                         for a in reference.get("level_artifacts", [])]} if reference else None,
                "reviewed_rules": selection_rules(game_id), "rules_source": "output/game-selection-20/selection.json",
                "level_annotations": level_annotations(game_id),
                "rule_archives": rule_archives(game_id), "goal_studies": goal_studies(game_id)}

    @router.patch("/benchmarks/{game_id}")
    def patch_benchmark(game_id: str, patch: BenchmarkPatch):
        _check_id(game_id)
        fields = patch.model_fields_set
        if not fields:
            raise HTTPException(400, "Nothing to update")
        with write_lock:
            data = load()
            entry = data["games"].get(game_id)
            if entry is None:
                raise HTTPException(404, "Unknown benchmark game")
            if "tier" in fields:
                entry["tier"], entry["tier_source"] = patch.tier, "manual"
            if "tags" in fields:
                if patch.tags is None:
                    raise HTTPException(422, "tags must be an object")
                vocabulary = data.get("tag_vocabulary", {})
                tags = {}
                for kind in ("mechanics", "properties"):
                    values = getattr(patch.tags, kind)
                    unknown = sorted(set(values) - set(vocabulary.get(kind, [])))
                    if unknown:
                        raise HTTPException(422, f"Unknown {kind} tags: {', '.join(unknown)}")
                    tags[kind] = [t for t in vocabulary[kind] if t in set(values)]
                entry["tags"], entry["tags_status"] = tags, "reviewed"
            if "notes" in fields:
                entry["notes"] = (patch.notes or "").strip()
            if "summary" in fields:
                entry["summary"] = " ".join((patch.summary or "").split())
                entry["summary_source"] = "manual"
            _write_json_atomic(games_path, data)
        by_game, _, _ = measured()
        return public(game_id, entry, by_game)

    @router.put("/benchmarks/{game_id}/rules")
    def edit_reviewed_rule(game_id: str, edit: RuleEdit):
        """Port of /__games/notes kind=rule: edit one reviewed rule in selection.json."""
        _check_id(game_id)
        path = root / "output/game-selection-20/selection.json"
        with write_lock:
            try:
                original_text = path.read_text(encoding="utf-8-sig")
            except OSError:
                raise HTTPException(404, "No reviewed rules notebook")
            selection = json.loads(original_text)
            game = next((g for g in selection.get("games", []) if g.get("id") == game_id), None)
            if game is None:
                raise HTTPException(404, "This game has no editable reviewed rules")
            rules = game.get("rules") or []
            if edit.index >= len(rules):
                raise HTTPException(404, "Unknown reviewed rule")
            if rules[edit.index] != edit.before:
                raise HTTPException(409, "This rule changed since you opened it. Reload and try again.")
            prefix = re.match(r"^\d+\.\s*", rules[edit.index])
            rules[edit.index] = (prefix.group(0) if prefix else "") + re.sub(r"^\d+\.\s*", "", edit.value.strip())
            _write_json_atomic(path, selection, "\r\n" if "\r\n" in original_text else "\n")
        return {"saved": rules[edit.index], "rules": rules, "file": "output/game-selection-20/selection.json"}

    def expire_sessions() -> None:
        now = time.monotonic()
        with sessions_lock:
            stale = [sid for sid, s in sessions.items() if now - s["touched"] > PLAY_IDLE_SECONDS]
            records = [sessions.pop(sid) for sid in stale]
        for record in records:
            close_scorecard(record)

    def close_scorecard(record: dict) -> None:
        try:
            post("/api/scorecard/close", {"card_id": record["card_id"]})
        except HTTPException:
            pass

    def frame_payload(session_id: str, record: dict, response: dict) -> dict:
        return {"session": session_id, "game_id": record["game_id"], "level": record.get("level"),
                **{k: response.get(k) for k in ("state", "levels_completed", "win_levels", "available_actions",
                                                "frame", "rendered_frame", "projection", "action_input")}}

    @router.post("/benchmarks/{game_id}/play")
    def start_play(game_id: str, start: PlayStart | None = Body(default=None)):
        _check_id(game_id)
        entry = load()["games"].get(game_id)
        if entry is None or not entry.get("arc_catalog", True):
            raise HTTPException(404, "This game is not playable through the ARC service")
        expire_sessions()
        with sessions_lock:
            if len(sessions) >= MAX_PLAY_SESSIONS:
                raise HTTPException(429, "Too many open games. Close a play session first.")
        level = start.level if start else None
        if level is not None and isinstance(entry.get("levels"), int) and level >= entry["levels"]:
            raise HTTPException(400, f"Level must be between 0 and {entry['levels'] - 1}")
        card = post("/api/scorecard/open", {"tags": ["workbench-manual-play"]})
        body = {"game_id": game_id, "card_id": card["card_id"]}
        if level is not None:
            body["level_index"] = level
        try:
            response = post("/api/cmd/RESET", body)
        except HTTPException:
            close_scorecard({"card_id": card["card_id"]})
            raise
        session_id = uuid.uuid4().hex
        record = {"game_id": game_id, "card_id": card["card_id"], "guid": response["guid"],
                  "level": level, "touched": time.monotonic(), "busy": threading.Lock()}
        with sessions_lock:
            sessions[session_id] = record
        return frame_payload(session_id, record, response)

    @router.post("/benchmarks/play/{session}/{action}")
    def play_action(session: str, action: str):
        action = action.upper()
        if action not in PLAY_ACTIONS:
            raise HTTPException(400, f"Unsupported action '{action}'")
        with sessions_lock:
            record = sessions.get(session)
        if record is None:
            raise HTTPException(404, "This play session expired. Start the game again.")
        if not record["busy"].acquire(blocking=False):
            raise HTTPException(409, "A move is already in progress.")
        try:
            record["touched"] = time.monotonic()
            if action == "RESET":
                response = post("/api/cmd/RESET", {"game_id": record["game_id"], "card_id": record["card_id"],
                                                   "guid": record["guid"]})
            else:
                response = post(f"/api/cmd/{action}", {"game_id": record["game_id"], "guid": record["guid"]})
        finally:
            record["busy"].release()
        return frame_payload(session, record, response)

    @router.delete("/benchmarks/play/{session}")
    def close_play(session: str):
        with sessions_lock:
            record = sessions.pop(session, None)
        if record:
            close_scorecard(record)
        return {"closed": record is not None}

    return router


router = create_router()
