"""AVO3's final solver, for information only (``--final-solver``).

After the last attempt, one more session starts from the best attempt's final workspace (its notes,
world_model.md and scripts), with no game moves, and is asked to write ``solver.py``. The solver is then
played once alone on a fresh game. Its levels are recorded in ``campaign/final_solver/summary.json``;
they are not the campaign's score. Any failure is recorded, never raised: the campaign has already ended.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from frameworks.avo.core.profile import load_profile
from frameworks.avo.evolution.solver_evaluation import evaluate_solver_workspace
from frameworks.avo.isolation import new_workspace
from frameworks.avo.run_once import PlayerRunSettings, execute_player_run

TASK = (
    "# Final task: write the solver\n\n"
    "The research attempts are over and you have no game moves left. Your workspace holds what earlier "
    "attempts learned: notes, world_model.md and any scripts. Using them, write solver.py for this game, "
    "as the task describes: it reads one JSON observation per line and prints one action per line. It will "
    "be played once, alone, on a fresh game from level 1, and should complete as many levels as it can. "
    "`observe` still shows the starting board. Archive the workspace before you finish."
)


def _source(evaluations: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    """The best attempt by fitness; on a tie the latest, which inherited the most."""
    best = None
    for item in evaluations:
        if best is None or float(item.get("fitness") or 0) >= float(best.get("fitness") or 0):
            best = item
    return best


def run_final_solver(*, root: Path, evaluations: tuple[dict[str, Any], ...], profile: str | Path,
                     profile_settings: Mapping[str, Any], player: PlayerRunSettings, max_steps: int) -> dict[str, Any]:
    out = root / "final_solver"
    out.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {"note": "information only, not the campaign score", "max_steps": max_steps}
    try:
        source = _source(evaluations)
        if source is None:
            raise RuntimeError("no completed attempt to start from")
        record["source_candidate"] = source["candidate_id"]
        archived = Path(str(source["run_dir"])) / "solver"
        workspace = Path(new_workspace()).resolve()
        if archived.is_dir():
            shutil.copytree(archived, workspace, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".avo_rpc", "__pycache__"))
        # The solver profile (not the research one): its prompt describes solver.py's contract.
        settings = replace(player, fitness="solver", base_prompt=PlayerRunSettings.base_prompt,
                           max_environment_steps=0, max_solver_self_checks=0, max_agent_turns=2,
                           final_world_model=False)
        session = execute_player_run(
            loaded_profile=load_profile(profile, profile_settings), output_dir=out / "session",
            workspace=workspace, settings=settings, candidate_id="final_solver", candidate_strategy=TASK,
            run_metadata={"source_candidate": source["candidate_id"]})
        solver_dir = session.output_dir / "workspace"
        record["solver_present"] = (solver_dir / "solver.py").is_file()
        scored = evaluate_solver_workspace(
            loaded_profile=load_profile(profile, profile_settings), workspace=solver_dir,
            output_dir=out / "evaluation", max_environment_steps=max_steps,
            max_wall_seconds=player.max_wall_seconds)
        score = dict(scored.score)
        record.update({"status": "completed", "levels_completed": score.get("solver_levels_completed"),
                       "win_levels": (score.get("environment_task") or {}).get("score", {}).get("win_levels"),
                       "success": scored.success, "environment_steps": scored.environment_steps,
                       "finish_reason": scored.finish_reason})
    except Exception as exc:  # noqa: BLE001 - recorded for the run page; the campaign result stands
        record.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})
    (out / "summary.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return record
