"""Levels as tasks: where a game starts, where it ends, the shortest solutions and the per-level score.

A player can start a PuzzleScript game at playable level k (``start_level``, 1-based; message screens
are not counted). The game shows that level and the total (``levels_completed`` starts at k-1 of
``win_levels``); reset and undo stay on level k. ``stop_after_levels`` counts from the start level, so
``start_level=k, stop_after_levels=1`` is the one-level task: it ends at level k's win and level k+1
is never shown. A run's ``result.json`` then lists each level it played (``level_scores``).

``SHORTEST`` holds the fewest moves that solve each level, found by breadth-first search over the
real engine (experiement/bfs_solver/stateful_solver.js, semantic mode; Modality agrees with
studies/thursday/modality.py). A level without a known value is absent: ``shortest`` returns None.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

# game id -> fewest moves for levels 1, 2, ... (None: not known). Computed 21 Oct 2026.
SHORTEST: dict[str, tuple[int | None, ...]] = {
    "ps_modality-v1": (6, 33, 66, 158),
    "ps_icecrates-v1": (4, 5, 12, 29, 8, 32),
    "ps_knightoban-v1": (20, 10, None, 41, None, 28),  # levels 3 and 5: search hit 10 min
}


def shortest(game_id: str, level: int) -> int | None:
    """The fewest moves that solve playable level ``level`` (1-based), or None when unknown."""
    table = SHORTEST.get(game_id, ())
    return table[level - 1] if 1 <= level <= len(table) else None


def stop_target(start_level: int, stop_after_levels: int) -> int:
    """The absolute ``levels_completed`` at which play ends (0 = play on)."""
    return start_level - 1 + stop_after_levels if stop_after_levels else 0


def start_note(start_level: int, win_levels: int) -> str:
    """The sentence that tells the player where the game starts; empty at level 1."""
    return f" The game starts at level {start_level} of {win_levels}." if start_level > 1 else ""


def level_scores(records: Iterable[Mapping[str, Any]], game_id: str, start_level: int = 1,
                 stop_after_levels: int = 0) -> list[dict[str, Any]]:
    """One entry per level played: solved, moves spent on it, and the shortest solution when known.

    ``records`` are transitions.jsonl rows (``before``/``after`` with ``levels_completed`` and
    ``win_levels``). A move belongs to the level it was taken on, so resets and undos count. ``ratio``
    is moves / shortest for a solved level with a known shortest solution.
    """
    moves: dict[int, int] = {}
    reached = start_level - 1
    win_levels = 0
    for record in records:
        before, after = record["before"], record["after"]
        level = int(before["levels_completed"]) + 1
        moves[level] = moves.get(level, 0) + 1
        reached = max(reached, int(after["levels_completed"]))
        win_levels = max(win_levels, int(after.get("win_levels") or 0))
    last = reached + 1  # the level play ended on, unless it ended on a win
    if win_levels:
        last = min(last, win_levels)
    target = stop_target(start_level, stop_after_levels)
    if target:
        last = min(last, target)
    scores = []
    for level in range(start_level, last + 1):
        best = shortest(game_id, level)
        solved = reached >= level
        used = moves.get(level, 0)
        scores.append({"level": level, "solved": solved, "moves": used, "shortest": best,
                       "ratio": round(used / best, 2) if solved and best else None})
    return scores


def result_fields(transitions: Path, game_id: str, start_level: int = 1, stop_after_levels: int = 0) -> dict[str, Any]:
    """The per-level fields of a run's result.json, from its transitions.jsonl.

    ``levels`` lists every level played; ``level_solved``/``level_moves``/``level_shortest``/``level_ratio``
    repeat the start level's entry, which is the whole score of a one-level task.
    """
    records = ([json.loads(line) for line in transitions.read_text(encoding="utf-8").splitlines() if line.strip()]
               if transitions.is_file() else [])
    scores = level_scores(records, game_id, start_level, stop_after_levels)
    first = scores[0]
    return {"start_level": start_level, "levels": scores, "level_solved": first["solved"],
            "level_moves": first["moves"], "level_shortest": first["shortest"], "level_ratio": first["ratio"]}
