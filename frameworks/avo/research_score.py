"""AVO's score: a candidate scores the most levels its research session completed, fewer actions breaking ties.

There is no solver: the research session tries to advance through the game itself, keeping
world_model.md. Solver-scored AVO was archived on 2 Nov 2026 (archive/avo-solver/).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def best_progress(history: Sequence[Any]) -> dict[str, int]:
    """The most levels completed at any point of a session, and the action that first reached them.

    A reset or a restored checkpoint can send the board back, so the last observation alone undercounts.
    """
    best = at = win_levels = 0
    for number, transition in enumerate(history, start=1):
        progress = transition.after.progress if isinstance(transition.after.progress, Mapping) else {}
        levels = int(progress.get("levels_completed") or 0)
        win_levels = max(win_levels, int(progress.get("win_levels") or 0))
        if levels > best:
            best, at = levels, number
    return {"best_levels_completed": best, "actions_to_best": at, "win_levels": win_levels}


def rank(evaluation: Mapping[str, Any]) -> tuple[float, float]:
    """max() key for the best evaluation: fitness, then fewer actions to reach it.

    Archived solver-scored evaluations have no ``actions_to_best``, so the earliest of equal fitness stays best.
    """
    actions = (evaluation.get("score") or {}).get("actions_to_best")
    return float(evaluation["fitness"]), -float(actions or 0)
