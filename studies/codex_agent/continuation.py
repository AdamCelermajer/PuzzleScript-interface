"""Explicit new-session continuation; never presented as the original thread."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from client.arc.types import GameAction
from client.engine.utils import last_grid


def load_parent(directory: str | Path) -> tuple[dict, list[dict]]:
    root = Path(directory).resolve()
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    if result.get("solved") or result.get("reason") != "step_budget_exhausted":
        raise ValueError("Continue only an unsolved run that exhausted its action budget")
    history = [json.loads(line) for line in (root / "transitions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if not history or len(history) != result["action_count"]:
        raise ValueError("Parent transition history is incomplete")
    return result, history


def seed_notes(parent: str | Path, target: Path) -> None:
    source = Path(parent).resolve() / "workspace"
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Parent notes contain a link")
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            destination = target / path.relative_to(source)
            if destination.exists():
                raise ValueError("Continuation requires an empty note workspace")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


def restore_game(env, frame, history: list[dict]):
    # Replaying on a new environment leaves the original run untouched. Check
    # every state, not just the last board; refuse nondeterministic restoration.
    for index, transition in enumerate(history, 1):
        if transition["action_index"] != index:
            raise ValueError("Parent action indices are not consecutive")
        if last_grid(frame.frame) != transition["before"]["grid"]:
            raise ValueError(f"Restoration mismatch before action {index}")
        frame = env.step(GameAction[transition["action"]])
        actual = {"grid": last_grid(frame.frame), "state": getattr(frame.state, "value", str(frame.state)),
                  "levels_completed": frame.levels_completed, "win_levels": frame.win_levels}
        if actual != transition["after"]:
            raise ValueError(f"Restoration mismatch after action {index}")
    return frame


def history_prompt(history: list[dict]) -> str:
    visible = [{"action_index": item["action_index"], "action": item["action"],
                "before": item["before"], "after": item["after"]} for item in history]
    return (
        f"This is a new-session continuation after {len(history)} prior game actions. "
        "The environment has been restored to the final recorded position. "
        "The action budget below is additional to those prior actions. "
        "Your saved notes have been carried over; read them before acting. "
        "The previous session's private reasoning is not available. "
        "Here is its recorded action and observation history:\n"
        + json.dumps(visible, separators=(",", ":")) + "\n\n"
    )
