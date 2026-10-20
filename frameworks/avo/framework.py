"""AVO campaign: an optimizer agent evolves the strategy of a player agent, and each
candidate is scored by a fresh run of the solver it leaves behind."""
from __future__ import annotations

import json
from pathlib import Path

from frameworks.base import Framework, Option

WORLD_MODEL_MODES = ("final-only", "between-hypotheses")
# Recorded harness names of campaigns launched before the harnesses package existed.
LEGACY_HARNESS = {"tools": "bare"}


def entry(spec: dict, resume: bool, results: Path, parent: Path) -> list[str]:
    options = spec["options"]
    wall = str(spec["max_wall_seconds"])
    argv = ["frameworks.avo.evolve", "--profile", "puzzlescript",
            "--set", f"game_id={spec['game_id']}", "--set", f"backend_url={spec['backend_url']}",
            "--output-dir", str(results / "campaign"), "--harness", spec["harness"],
            "--player-model", spec["model"], "--player-effort", spec["effort"],
            "--optimizer-model", spec["optimizer_model"], "--optimizer-effort", spec["optimizer_effort"],
            "--world-model-mode", options["world_model_mode"],
            "--max-evaluations", str(options["max_evaluations"]),
            "--player-max-environment-steps", str(options["research_moves"]),
            "--fresh-solver-max-environment-steps", str(options["solver_moves"]),
            "--solver-self-check-max-environment-steps", str(options["solver_moves"]),
            "--max-wall-seconds", wall, "--player-max-wall-seconds", wall,
            "--provider", spec["provider"]]
    if resume:
        argv.append("--resume-saved-campaign")
    return argv


def check_restart(spec: dict, output: Path) -> None:
    """A resumed campaign keeps its game, harness, provider and world-model condition."""
    saved_path = output / "campaign" / "evolution_config.json"
    if not saved_path.is_file() or not (output / "campaign" / "lineage.json").is_file():
        raise ValueError(f"--resume needs a saved campaign at {output / 'campaign'}")
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    harness = saved.get("harness", "codex")
    harness = LEGACY_HARNESS.get(harness, harness)
    if harness != spec["harness"] or saved.get("provider", "") != spec["provider"]:
        raise ValueError(f"Cannot change the harness while resuming (saved: {harness}, requested: {spec['harness']})")
    if (saved.get("profile_settings") or {}).get("game_id") not in {None, spec["game_id"]}:
        raise ValueError("Cannot change the game while resuming a campaign")
    if saved.get("world_model_mode", spec["options"]["world_model_mode"]) != spec["options"]["world_model_mode"]:
        raise ValueError("Cannot change the world-model condition while resuming a campaign")


AVO = Framework(
    id="avo",
    label="AVO",
    description="An optimizer agent evolves the player's strategy; each candidate leaves a solver.py "
                "that is scored by a fresh run.",
    options=(
        Option("max_evaluations", "int", 8, "candidate strategies evaluated", minimum=1, maximum=100),
        Option("research_moves", "int", 400, "game actions per research run", minimum=1, maximum=10_000),
        Option("solver_moves", "int", 400, "game actions per fresh solver run", minimum=1, maximum=20_000),
        Option("world_model_mode", "str", "final-only", "when the optimizer writes its world-model report",
               choices=WORLD_MODEL_MODES),
    ),
    entry=entry,
    optimizer=True,
    artifact="campaign",
    restart="resume",
    check_restart=check_restart,
)
