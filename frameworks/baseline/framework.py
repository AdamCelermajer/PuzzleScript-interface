"""Baseline: the coding agent plays the game directly, one action per turn.

With ``notes`` the agent also keeps a notes file across turns (formerly "baseline-plus").
"""
from __future__ import annotations

from pathlib import Path

from frameworks.base import Framework, Option


def entry(spec: dict, resume: bool, results: Path, parent: Path) -> list[str]:
    options = spec["options"]
    argv = ["frameworks.baseline.run", "--no-window", "--harness", spec["harness"], "--model", spec["model"],
            "--effort", spec["effort"], "--game-id", spec["game_id"], "--backend-url", spec["backend_url"],
            "--max-steps", str(options["max_steps"]), "--max-wall-seconds", str(spec["max_wall_seconds"]),
            "--output-dir", str(results), "--provider", spec["provider"]]
    if options["notes"]:
        argv.append("--notes")
    if spec.get("continued_from"):
        argv += ["--continue-from", str(parent)]
    return argv


def check_restart(spec: dict, parent: Path) -> None:
    if not (parent / "run_config.json").is_file():
        raise ValueError(f"{parent} is not a finished baseline run (no run_config.json)")


BASELINE = Framework(
    id="baseline",
    label="Baseline",
    description="The coding agent plays directly: one action per turn, nothing else.",
    options=(
        Option("max_steps", "int", 200, "game actions", minimum=1, maximum=10_000),
        Option("notes", "bool", False, "a notes file the agent reads and edits across turns"),
    ),
    entry=entry,
    restart="continue",
    check_restart=check_restart,
    variant=lambda options: "Baseline+" if options.get("notes") else "Baseline",
)
