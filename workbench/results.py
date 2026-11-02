"""Results matrix for the workbench home: games x (harness, model) -> best levels solved.

Computed from the run catalog on request (cached briefly), never stored. A cell's level
count is what the run recorded: levels completed for direct play, best fresh-solver fitness
for campaigns. A one-level task (catalog ``level``) gets its own row, "game · level k", whose cells
count 1 when that level was solved, so the same level lines up across configurations and frameworks.
Runs without `run_spec.json` (before the harness revamp) are archive runs and
are only included with `archive=1`.
"""
from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Query

from workbench.catalog import HARNESS_IDS, ROOT, read_json, snapshot

CACHE_SECONDS = 15
TIER_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def _count(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return int(value)


def run_levels(run: dict) -> int | None:
    return _count(run.get("best_fitness") if run.get("kind") == "avo" else run.get("levels"))


def run_win_levels(run: dict, games: dict) -> int | None:
    if run.get("kind") != "avo":
        total = _count(run.get("recorded_win_levels"))
    else:
        total = None
        for evaluation in (run.get("result_inputs") or {}).get("evaluations") or []:
            score = evaluation.get("score") or {}
            for value in (((score.get("environment_task") or {}).get("score") or {}).get("win_levels"),
                          score.get("win_levels"), (score.get("research_score") or {}).get("win_levels")):
                if _count(value):
                    total = _count(value)
                    break
            if total:
                break
    if not total:
        total = _count((games.get(run.get("game_id")) or {}).get("levels"))
    return total or None


def is_archive(run: dict) -> bool:
    return run.get("spec_source") != "run_spec" or run.get("archived") is True


def harness_rank(harness: str) -> int:
    return HARNESS_IDS.index(harness) if harness in HARNESS_IDS else len(HARNESS_IDS)


def build_matrix(runs: list[dict], games: dict, archive: bool = False, variant: str | None = None) -> dict:
    cells: dict[str, dict] = {}
    columns: dict[tuple[str, str], dict] = {}
    rows: dict[str, tuple[str, int | None]] = {}
    for run in runs:
        game_id, model = run.get("game_id"), run.get("model")
        harness = run.get("harness") or run.get("agent_backend")
        if not game_id or not model or not harness or "has_result" not in run:
            continue  # queued children without artifacts are not runs yet
        if is_archive(run) and not archive:
            continue
        if variant and run.get("variant") != variant:
            continue
        level = _count(run.get("level"))
        row = f"{game_id}#L{level}" if level else game_id
        key = f"{row}|{harness}|{model}"
        if level:
            # Runs from before per-level scores: the level is solved once levels_completed reaches it.
            score = run.get("level_score") or {"solved": (_count(run.get("levels")) or 0) >= level}
            levels, total = int(score.get("solved") is True), 1
        else:
            levels, total = run_levels(run), run_win_levels(run, games)
        cell = cells.setdefault(key, {"best_levels": None, "win_levels": total, "runs": 0, "best_run_id": None,
                                      "solved": False, "run_ids": [], "_rank": None})
        cell["runs"] += 1
        cell["run_ids"].append((run.get("modified") or 0, run["id"]))
        solved = levels == 1 if level else run.get("solved") is True
        cell["solved"] = cell["solved"] or solved
        rank = (levels if levels is not None else -1, solved, run.get("modified") or 0)
        if cell["_rank"] is None or rank > cell["_rank"]:
            cell.update(_rank=rank, best_levels=levels, best_run_id=run["id"])
            if total:
                cell["win_levels"] = total
        column = columns.setdefault((harness, model), {"harness": harness, "model": model,
                                                       "label": model.split("/")[-1], "runs": 0})
        column["runs"] += 1
        rows[row] = (game_id, level)
    for cell in cells.values():
        cell.pop("_rank")
        cell["run_ids"] = [run_id for _, run_id in sorted(cell["run_ids"], reverse=True)][:20]
    game_rows = []
    for row, (game_id, level) in rows.items():
        entry = games.get(game_id) or {}
        totals = [c["win_levels"] for k, c in cells.items() if k.startswith(row + "|") and c["win_levels"]]
        game_rows.append({"game_id": game_id, "key": row, "level": level, "title": entry.get("title") or game_id,
                          "tier": entry.get("tier"),
                          "win_levels": 1 if level else _count(entry.get("levels")) or (max(totals) if totals else None)})
    game_rows.sort(key=lambda g: (TIER_ORDER.get(g["tier"], 3), g["title"].casefold(), g["level"] or 0))
    ordered = sorted(columns.values(), key=lambda c: (harness_rank(c["harness"]), c["harness"], c["model"]))
    return {"games": game_rows, "columns": ordered, "cells": cells}


def create_router(root: Path = ROOT, run_snapshot: Callable[[], dict] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/workbench")
    cache: dict = {}
    lock = threading.Lock()

    def catalog_runs() -> tuple[list[dict], float]:
        with lock:
            if cache and time.monotonic() - cache["at"] < CACHE_SECONDS:
                return cache["runs"], cache["checked_at"]
            data = run_snapshot() if run_snapshot else snapshot(root, containers={})
            cache.update(at=time.monotonic(), runs=data.get("runs", []), checked_at=data.get("checked_at", time.time()))
            return cache["runs"], cache["checked_at"]

    @router.get("/results/matrix")
    def results_matrix(archive: int = Query(0, ge=0, le=1), variant: str | None = Query(None, max_length=80)):
        runs, checked_at = catalog_runs()
        games = read_json(root / "benchmark/games.json").get("games") or {}
        return {**build_matrix(runs, games, archive=bool(archive), variant=variant), "archive": bool(archive),
                "variant": variant, "checked_at": checked_at}

    return router


router = create_router()
