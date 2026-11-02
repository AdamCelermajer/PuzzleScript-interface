"""Baseline: the minimal PuzzleScript harness, with no outer method.

``driver`` sets who drives the game: ``controller`` (run.py: we send one frame per call and get
one action back, in one conversation, with a ``notes/`` folder the agent is asked to keep its
working memory in) or ``agent`` (agent.py: the agent plays through ``python game.py`` in a folder
that persists for the whole run). The controller always has its notes folder; the plain mode
without it was removed on 21 Oct 2026 (older runs record ``notes: false``).
``stop_after_levels`` ends the game once that many levels are completed, without showing the next
level. ``start_level`` opens the game at that level and ``stop_after_levels`` counts from it;
``one_level`` is the one-level task (stop after 1), scored per level in result.json
(frameworks/levels.py). ``memento`` (controller only) opens a fresh session every turn with the same
system prompt and folder, and tells the agent that only its folder (notes/) carries over. With the agent driver, ``start`` names a repository folder whose files are in the agent's
folder from the start (copied into the run as ``start/``).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from frameworks.base import Framework, Option

ROOT = Path(__file__).resolve().parents[2]
START = "start"  # the run directory's copy of the start folder; the agent's folder starts with it


def entry(spec: dict, resume: bool, results: Path, parent: Path) -> list[str]:
    options = spec["options"]
    if options.get("driver") == "agent":
        if spec.get("continued_from"):
            raise ValueError("Runs where the agent drives cannot be continued; start a new run")
        argv = ["frameworks.baseline.agent", "--harness", spec["harness"], "--model", spec["model"],
                "--effort", spec["effort"], "--game-id", spec["game_id"], "--backend-url", spec["backend_url"],
                "--max-steps", str(options["max_steps"]), "--max-wall-seconds", str(spec["max_wall_seconds"]),
                "--output-dir", str(results), "--provider", spec["provider"]]
        if options.get("start"):
            argv += ["--harness-dir", str(results / START), "--start", options["start"]]
        return argv + level_argv(options)
    argv = ["frameworks.baseline.run", "--notes", "--harness", spec["harness"], "--model", spec["model"],
            "--effort", spec["effort"], "--game-id", spec["game_id"], "--backend-url", spec["backend_url"],
            "--max-steps", str(options["max_steps"]), "--max-wall-seconds", str(spec["max_wall_seconds"]),
            "--output-dir", str(results), "--provider", spec["provider"]]
    argv += level_argv(options)
    if options.get("memento"):
        argv.append("--memento")
    if spec.get("continued_from"):
        argv += ["--continue-from", str(parent)]
    return argv


def level_argv(options: dict) -> list[str]:
    """Start level and level end; options of runs before 22 Oct 2026 have neither start_level nor one_level."""
    argv = []
    if options.get("start_level", 1) > 1:
        argv += ["--start-level", str(options["start_level"])]
    stop = 1 if options.get("one_level") else options.get("stop_after_levels")
    if stop:
        argv += ["--stop-after-levels", str(stop)]
    return argv


def check(options: dict) -> None:
    if options["one_level"] and options["stop_after_levels"]:
        raise ValueError("--one-level already ends the game after one level; leave --stop-after-levels at 0")
    if options["memento"] and options["driver"] != "controller":
        raise ValueError("--memento applies only to --driver controller (one action per call)")
    if options["driver"] != "agent" and options["start"]:
        raise ValueError("--start applies only to --driver agent")
    if options["start"]:
        folder = (ROOT / options["start"]).resolve()
        if not folder.is_relative_to(ROOT) or not folder.is_dir():
            raise ValueError(f"--start must name a folder in the repository, not {options['start']!r}")


def prepare(spec: dict, output: Path) -> None:
    """Copy the start folder into the run directory; the agent's folder gets exactly this copy."""
    if spec["options"].get("start"):
        shutil.copytree(ROOT / spec["options"]["start"], output / START, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def check_restart(spec: dict, parent: Path) -> None:
    if not (parent / "run_config.json").is_file():
        raise ValueError(f"{parent} is not a finished baseline run (no run_config.json)")


def variant(options: dict) -> str:
    if options.get("driver") == "agent":
        label = "Baseline · agent" + (" · notes" if options.get("notes") else "")
    else:  # runs before 21 Oct 2026 record notes; the controller has always had them since
        label = "Baseline" if options.get("notes", True) else "Baseline · no notes (old)"
        if options.get("memento"):
            label += " · memento"
    if options.get("start"):
        label += f" · start={Path(options['start']).name}"
    start = options.get("start_level", 1)
    if options.get("one_level"):
        label += f" · level {start}"
    elif options.get("stop_after_levels"):
        label += (f" · levels {start}-{start + options['stop_after_levels'] - 1}" if start > 1
                  else f" · first {options['stop_after_levels']} levels")
    elif start > 1:
        label += f" · from level {start}"
    return label


BASELINE = Framework(
    id="baseline",
    label="Baseline",
    description="The minimal harness: the coding agent plays the game itself, nothing else. Driver: we send one "
                "frame per call and it keeps notes in its folder (controller), or it plays through a game command "
                "in its own folder (agent).",
    options=(
        Option("max_steps", "int", 200, "game actions", minimum=1, maximum=10_000),
        Option("driver", "str", "controller", "who drives the game: we send one frame per call, or the agent plays "
               "through `python game.py` in its own folder", choices=("controller", "agent")),
        Option("memento", "bool", False, "controller driver: a fresh session every turn with the same system "
               "prompt and folder; the agent is told it forgets everything but its folder (notes/)"),
        Option("start", "str", "", "agent driver: a repository folder (e.g. studies/thursday/start/rules) whose "
               "files are in the agent's folder from the start"),
        Option("stop_after_levels", "int", 0, "end the game once this many levels are completed, counted from the "
               "start level, without showing the next one (0 = play on)", minimum=0, maximum=100),
        Option("start_level", "int", 1, "open the game at this level (1-based); resets stay on it", minimum=1,
               maximum=100),
        Option("one_level", "bool", False, "play only the start level: the game ends at its win, the next level "
               "is never shown, and the run is scored on that level"),
    ),
    entry=entry,
    restart="continue",
    check_restart=check_restart,
    variant=variant,
    check=check,
    prepare=prepare,
)
