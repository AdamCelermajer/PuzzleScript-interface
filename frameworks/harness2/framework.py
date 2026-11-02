"""The launcher contract; importing it does not require the upstream package."""
from __future__ import annotations

import json
from pathlib import Path

from frameworks.base import Framework, Option


def entry(spec: dict, resume: bool, results: Path, parent: Path) -> list[str]:
    if spec["harness"] != "opencode":
        raise ValueError("Harness² requires --harness opencode for both player and improver")
    argv = ["frameworks.harness2.run", "--output-dir", str(results)]
    for key in ("harness", "model", "effort", "optimizer_model", "optimizer_effort", "game_id",
                "backend_url", "max_wall_seconds", "provider"):
        argv += ["--" + key.replace("_", "-"), str(spec[key])]
    for key, value in spec["options"].items():
        if isinstance(value, bool):
            argv += ["--" + key.replace("_", "-")] if value else []
        else:
            argv += ["--" + key.replace("_", "-"), str(value)]
    if resume:
        argv.append("--resume")
    return argv


def check_restart(spec: dict, output: Path) -> None:
    saved = output / "harness2_config.json"
    if not saved.is_file():
        raise ValueError(f"--resume needs a saved Harness² run at {output}")
    old = json.loads(saved.read_text(encoding="utf-8"))
    for key in ("harness", "model", "effort", "optimizer_model", "optimizer_effort", "game_id",
                "backend_url", "provider", "max_wall_seconds"):
        if old.get(key) != spec.get(key):
            raise ValueError(f"Cannot change {key} while resuming Harness²")
    # Runs saved before an option existed resume with its default.
    if HARNESS2.check_options(old.get("options") or {}) != HARNESS2.check_options(spec.get("options") or {}):
        raise ValueError("Cannot change options while resuming Harness²")


HARNESS2 = Framework(
    id="harness2", label="Harness²",
    description="An improver edits the player's harness files from contrasts between scored runs; "
                "the best harness is re-run fresh.",
    options=(
        Option("k", "int", 1, "4k player runs + 1 fresh run, 3k improver sessions", minimum=1, maximum=5),
        Option("recursion", "str", "parallel", choices=("parallel", "sequential")),
        Option("max_steps", "int", 200, "game actions per player run", minimum=1, maximum=10_000),
        Option("stop_after_levels", "int", 0, "end each player run once this many levels are completed, without "
               "showing the next one (0 = play on)", minimum=0, maximum=100),
        Option("levels", "int", 0, "0 = the whole game is one task; N = levels 1..N, each its own task, in order, "
               "each starting from the previous level's kept harness", minimum=0, maximum=100),
        Option("budgets", "str", "30,50,100,200,500", "per-level runs: game actions of each round, in order; "
               "the budget never goes down, and a new level starts at the one the last level ended on"),
        Option("skip_below_shortest", "bool", False, "per-level runs: skip budgets below the level's shortest solution"),
        Option("max_rounds", "int", 5, "per-level runs: coaching rounds per level at most (the last budget repeats)",
               minimum=1, maximum=20),
    ),
    entry=entry, optimizer=True, restart="resume", check_restart=check_restart,
)
