"""AVO campaign: an optimizer agent evolves the strategy of a player agent, and each
candidate is scored by a fresh run of the solver it leaves behind, or (``fitness=research``,
frameworks/avo/research_score.py) by the levels its research session completes, with no solver."""
from __future__ import annotations

import json
from pathlib import Path

from frameworks.avo.research_score import FITNESS_MODES
from frameworks.base import Framework, Option

WORLD_MODEL_MODES = ("final-only", "between-hypotheses")
# Recorded harness names of campaigns launched before the harnesses package existed.
LEGACY_HARNESS = {"tools": "bare"}


def research_schedule(raw: str) -> list[int]:
    """'30,50,100' -> [30, 50, 100]: research moves per attempt, in order (empty = none)."""
    values = [part.strip() for part in str(raw or "").split(",") if part.strip()]
    try:
        schedule = [int(value) for value in values]
    except ValueError:
        raise ValueError("--research-moves-schedule must be comma-separated integers, e.g. 30,50,100") from None
    if any(value < 1 or value > 10_000 for value in schedule):
        raise ValueError("--research-moves-schedule values must be between 1 and 10000")
    return schedule


def entry(spec: dict, resume: bool, results: Path, parent: Path) -> list[str]:
    options = spec["options"]
    wall = str(spec["max_wall_seconds"])
    schedule = research_schedule(options.get("research_moves_schedule", ""))
    argv = ["frameworks.avo.evolve", "--profile", "puzzlescript",
            "--set", f"game_id={spec['game_id']}", "--set", f"backend_url={spec['backend_url']}",
            "--output-dir", str(results / "campaign"), "--harness", spec["harness"],
            "--player-model", spec["model"], "--player-effort", spec["effort"],
            "--optimizer-model", spec["optimizer_model"], "--optimizer-effort", spec["optimizer_effort"],
            "--world-model-mode", options["world_model_mode"],
            "--fitness", options.get("fitness", "solver"),  # specs before 21 Oct 2026 have no fitness
            # A schedule sets one attempt per budget.
            "--max-evaluations", str(len(schedule) if schedule else options["max_evaluations"]),
            "--player-max-environment-steps", str(schedule[0] if schedule else options["research_moves"]),
            "--fresh-solver-max-environment-steps", str(options["solver_moves"]),
            "--solver-self-check-max-environment-steps", str(options["solver_moves"]),
            "--max-wall-seconds", wall, "--player-max-wall-seconds", wall,
            "--provider", spec["provider"]]
    if schedule:
        argv += ["--research-moves-schedule", ",".join(map(str, schedule))]
    if options.get("attempt_world_model"):
        argv.append("--attempt-world-model")
    if options.get("final_solver"):
        argv.append("--final-solver")
    if options.get("continue_levels"):
        argv.append("--continue-levels")
    if resume:
        argv.append("--resume-saved-campaign")
    return argv


def check_restart(spec: dict, output: Path) -> None:
    """A resumed campaign keeps its game, harness, provider, world-model condition and fitness."""
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
    if saved.get("fitness", "solver") != spec["options"].get("fitness", "solver"):
        raise ValueError("Cannot change the fitness while resuming a campaign")
    if saved.get("research_moves_schedule", []) != research_schedule(spec["options"].get("research_moves_schedule", "")):
        raise ValueError("Cannot change the research budget schedule while resuming a campaign")
    if saved.get("continue_levels", False) != spec["options"].get("continue_levels", False):
        raise ValueError("Cannot change continue_levels while resuming a campaign")


def variant(options: dict) -> str:
    """Campaigns from before the fitness option were all scored by their solver."""
    label = "AVO · research score" if options.get("fitness") == "research" else "AVO · solver score"
    return label + (" · continue levels" if options.get("continue_levels") else "")


AVO = Framework(
    id="avo",
    label="AVO",
    description="An optimizer agent evolves the player's strategy; each candidate leaves a solver.py "
                "that is scored by a fresh run, or (research score) is scored by the levels its research "
                "session completes.",
    options=(
        Option("max_evaluations", "int", 8, "candidate strategies evaluated", minimum=1, maximum=100),
        Option("research_moves", "int", 400, "game actions per research run", minimum=1, maximum=10_000),
        Option("solver_moves", "int", 400, "game actions per fresh solver run", minimum=1, maximum=20_000),
        Option("world_model_mode", "str", "final-only", "when the optimizer writes its world-model report",
               choices=WORLD_MODEL_MODES),
        Option("fitness", "str", "solver", "what scores a candidate: the levels its solver.py completes from a "
               "fresh reset, or the levels its research session completes (no solver)", choices=FITNESS_MODES),
        Option("research_moves_schedule", "str", "", "research moves per attempt, in order, e.g. 30,50,100,200,500; "
               "one attempt per value (overrides max_evaluations and research_moves); empty = the same budget "
               "every attempt"),
        Option("attempt_world_model", "bool", False, "the research player writes world_model.md at the end of "
               "every attempt; each attempt's copy is kept"),
        Option("final_solver", "bool", False, "after the last attempt the player writes solver.py from what it "
               "learned; it is played once alone on a fresh game (solver_moves), for information, not the score"),
        Option("continue_levels", "bool", False, "each research session starts at the level where the previous "
               "one stopped instead of level 1 (research score: the farthest level reached); solvers and their "
               "self-checks are still played from level 1"),
    ),
    entry=entry,
    optimizer=True,
    artifact="campaign",
    restart="resume",
    check_restart=check_restart,
    variant=variant,
)
