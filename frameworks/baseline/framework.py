"""Baseline: the coding agent plays the game itself, with no outer method.

``driver`` sets who drives the game: ``controller`` (run.py: we send one frame per call and get
one action back) or ``agent`` (agent.py: the agent plays through ``python game.py`` in a folder
that persists for the whole run). ``notes`` adds the notes instruction (formerly "baseline-plus").
"""
from __future__ import annotations

from pathlib import Path

from frameworks.base import Framework, Option


def entry(spec: dict, resume: bool, results: Path, parent: Path) -> list[str]:
    options = spec["options"]
    if options.get("driver") == "agent":
        if spec.get("continued_from"):
            raise ValueError("Runs where the agent drives cannot be continued; start a new run")
        argv = ["frameworks.baseline.agent", "--harness", spec["harness"], "--model", spec["model"],
                "--effort", spec["effort"], "--game-id", spec["game_id"], "--backend-url", spec["backend_url"],
                "--max-steps", str(options["max_steps"]), "--max-wall-seconds", str(spec["max_wall_seconds"]),
                "--output-dir", str(results), "--provider", spec["provider"]]
        return argv + (["--notes"] if options["notes"] else [])
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
    description="The coding agent plays the game itself, nothing else. Driver: we send one frame per call "
                "(controller), or the agent plays through a game command in its own folder (agent).",
    options=(
        Option("max_steps", "int", 200, "game actions", minimum=1, maximum=10_000),
        Option("notes", "bool", False, "a notes file the agent reads and edits across turns"),
        Option("driver", "str", "controller", "who drives the game: we send one frame per call, or the agent plays "
               "through `python game.py` in its own folder", choices=("controller", "agent")),
    ),
    entry=entry,
    restart="continue",
    check_restart=check_restart,
    variant=lambda options: ("Baseline+" if options.get("notes") else "Baseline")
    + (" · agent" if options.get("driver") == "agent" else ""),
)
