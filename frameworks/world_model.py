"""One world-model file for every player: its format, the instruction to keep it, and copies during play.

Every player (Baseline's turn-based player, the agentic player, AVO's research session) keeps one
research-note file as its current model of the game. ``Snapshots`` copies that file after every
``EVERY`` game actions, right after each completed level and at the end, into
``<output>/world_model_snapshots/``, so a run shows what its player believed and when.
"""
from __future__ import annotations

import shutil
from pathlib import Path

NAME = "world_model.md"
SNAPSHOT_DIR = "world_model_snapshots"
EVERY = 100  # game actions between copies


def keep_instruction(path: str = NAME) -> str:
    """The in-game instruction: keep the file current while playing."""
    return (
        f"Keep {path} as your current model of the game, in research-note style: the objective, the "
        "objects and state, controls, movement and interactions, goal and level transitions, undo or "
        "history effects, and what is still uncertain. Separate observed rules from hypotheses. Write it "
        "before your first game action, read it before deciding, and update it whenever a move confirms "
        "or breaks a rule, your plan changes, you reach a dead end, or a level changes."
    )


def final_prompt(path: str = NAME) -> str:
    """The end-of-game report, in the research-note format the AVO optimizer has always used."""
    return (
        f"Write {path} in your current workspace now. Describe your inferred game rules "
        "for a reader who has not seen the run. Use a concise Markdown research-note style: "
        "start with the objective and the best evaluated outcome, then explain the objects and "
        "state, controls, movement and interactions, goal and level transitions, and any undo or "
        "history effects. Include observation quirks only when they matter to the rules. "
        "Describe any critical discovery, and end with remaining uncertainty. Use only headings "
        "relevant to this game. "
        "Explain important interactions step by step and give a few decisive observations, while "
        "keeping exhaustive traces, level maps, RGB values, API schemas, and solver implementation "
        "details out of the main report. Clearly separate observed rules from hypotheses; do not "
        "invent behavior for unseen situations. Aim for roughly 400–900 words unless the game's "
        "complexity requires more. Save the file before optional further checking, then refine it "
        "with any remaining time."
    )


class Snapshots:
    """Copies of a player's world-model file at fixed points of play; skipped while it does not exist."""

    def __init__(self, source: Path, output_dir: Path, every: int | None = None) -> None:
        self.source, self.target = Path(source), Path(output_dir) / SNAPSHOT_DIR
        self.every = EVERY if every is None else every

    def _copy(self, name: str) -> None:
        if not self.source.is_file():
            return
        try:
            self.target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.source, self.target / name)
        except OSError:  # a copy is best effort; it must never break the game it observes
            pass

    def after_action(self, actions: int, levels_before: float, levels_after: float) -> None:
        """Call after each game action, with the total actions taken and the levels before and after it."""
        if levels_after > levels_before:
            self._copy(f"level-{int(levels_after)}-a{actions:04d}.md")
        if self.every and actions % self.every == 0:
            self._copy(f"a{actions:04d}.md")

    def final(self) -> None:
        self._copy("final.md")
