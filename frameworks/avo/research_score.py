"""AVO's research-score variant: no solver; a candidate scores the levels its research session reaches.

``fitness=solver`` (the default) is AVO as designed: the research session writes solver.py and the
candidate's score is the levels that solver completes from a fresh reset. ``fitness=research`` drops
the solver: the research session tries to advance through the game itself, keeping world_model.md,
and the candidate's score is the most levels it completed during research, fewer actions breaking
ties. Its prompts are prompts/*_research.txt and the profile's prompt_research.md.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

FITNESS_MODES = ("solver", "research")
PROMPTS = Path(__file__).resolve().parent / "prompts"
BASE_PROMPT = PROMPTS / "base_agent_research.txt"
OUTER_PROMPT = PROMPTS / "outer_optimizer_research.txt"
ENVIRONMENT_PROMPT = "prompt_research.md"  # next to the profile's own prompt

RESEARCH_OBJECTIVE = (
    "Advance as far as possible through the game during each research session, building on what "
    "earlier candidates learned. There is no solver: the levels completed during research are the "
    "score (fewer actions breaks ties). Keep world_model.md up to date as you learn."
)


class ResearchObjective:
    """An environment profile with the research objective; everything else is the wrapped profile's."""

    objective = RESEARCH_OBJECTIVE

    def __init__(self, profile: Any) -> None:
        self._profile = profile

    def __getattr__(self, name: str) -> Any:
        return getattr(self._profile, name)


def research_profile(loaded: Any) -> Any:
    """A loaded profile (core.profile.LoadedProfile) with the research objective and task prompt."""
    path = loaded.prompt_path.with_name(ENVIRONMENT_PROMPT)
    return replace(loaded, implementation=ResearchObjective(loaded.implementation),
                   prompt=path.read_text(encoding="utf-8").strip(), prompt_path=path,
                   prompt_hash=hashlib.sha256(path.read_bytes()).hexdigest())


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
    """max() key for the best evaluation: fitness, then (research score) fewer actions to reach it.

    Solver-scored evaluations have no ``actions_to_best``, so the earliest of equal fitness stays best.
    """
    actions = (evaluation.get("score") or {}).get("actions_to_best")
    return float(evaluation["fitness"]), -float(actions or 0)
