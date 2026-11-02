from __future__ import annotations

import json
import shutil
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from frameworks.avo.core.profile import load_profile
from frameworks.avo.evolution.candidate import CandidateEvaluation, RunCandidate
from frameworks.avo.evolution.solver_evaluation import SolverEvaluation, evaluate_solver_workspace
from frameworks.avo.run_once import PlayerRunSettings, execute_player_run
from frameworks.avo.isolation import new_workspace, cleanup_private_directory


class RunCandidateEvaluator(Protocol):
    def evaluate(
        self,
        candidate: RunCandidate,
        run_dir: Path,
    ) -> CandidateEvaluation: ...


@dataclass(frozen=True)
class PlayerEvaluationConfig:
    profile: str | Path
    profile_settings: Mapping[str, Any]
    player: PlayerRunSettings
    fresh_solver_max_environment_steps: int = 1_500
    # continue_levels: each research session starts at the level where the previous one stopped (frameworks/levels.py);
    # this file records that level across evaluations and resumes. The solver is still scored from level 1.
    level_progress: Path | None = None


def research_start_level(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 1
    return int(json.loads(path.read_text(encoding="utf-8")).get("next_start_level", 1))


class CandidateEvaluator:
    """Trusted evaluation of a complete run candidate in a fresh environment."""

    def __init__(self, config: PlayerEvaluationConfig) -> None:
        self.config = config

    def evaluate(
        self,
        candidate: RunCandidate,
        run_dir: Path,
        research_moves: int | None = None,
    ) -> CandidateEvaluation:
        # A research budget schedule (AVO3) sets this attempt's moves.
        player = self.config.player if research_moves is None else replace(
            self.config.player, max_environment_steps=research_moves)
        start_level = research_start_level(self.config.level_progress)
        # Loading here, rather than in __init__, constructs a fresh profile/environment
        # for every x_i.
        loaded = load_profile(self.config.profile, {**self.config.profile_settings, "start_level": start_level}
                              if start_level > 1 else self.config.profile_settings)
        # AVO's research score (frameworks/avo/research_score.py): no solver; the research run is scored.
        research = player.fitness == "research"
        generation_dir = run_dir.resolve()
        clean_layout = generation_dir == candidate.root.resolve()
        research_dir = generation_dir / "research" if clean_layout else generation_dir
        evaluation_dir = (
            generation_dir / "evaluation"
            if clean_layout
            else generation_dir / "solver_evaluation"
        )
        research_dir.mkdir(parents=True, exist_ok=True)
        if not research:
            evaluation_dir.mkdir(parents=True, exist_ok=True)
        # Keep work outside the repository's AGENTS/config chain. Linux cleanup
        # follows verified archival; Windows retains its ACL-safe behavior.
        with nullcontext(new_workspace()) as raw:
            workspace = Path(raw).resolve()
            if candidate.workspace_path.is_dir():
                shutil.copytree(candidate.workspace_path, workspace, dirs_exist_ok=True)
            result = execute_player_run(
                loaded_profile=loaded,
                output_dir=research_dir,
                workspace=workspace,
                settings=player,
                candidate_id=candidate.candidate_id,
                candidate_strategy=candidate.strategy(),
                run_metadata={"parent_ids": list(candidate.parent_ids)},
            )
            if self.config.level_progress is not None:
                # The next session starts at the level this one stopped on (never before this one's start).
                reached, total = int(result.summary["best_levels_completed"]), int(result.summary["win_levels"])
                next_level = max(start_level, min(reached + 1, total) if total else reached + 1)
                self.config.level_progress.write_text(json.dumps({
                    "next_start_level": next_level, "after_candidate": candidate.candidate_id}), encoding="utf-8")
            archive_path = research_dir / "workspace_archive.json"
            if archive_path.is_file():
                archive_report = json.loads(archive_path.read_text(encoding="utf-8"))
                unarchived = [name for name in archive_report["skipped"]
                              if name != ".avo_rpc" and not name.startswith(".avo_rpc/")]
                if not unarchived and not archive_report["preserved"]:
                    cleanup_private_directory(workspace)

            # The researching Codex player's progress is evidence, not fitness.
            # Reloading the profile creates a second fresh game in which only the
            # archived solver may act. Only progress in this fresh game owns fitness.
            # Under the research score there is no solver: the research progress is the fitness.
            # Either way the final workspace goes to solver/, which children inherit.
            archived_workspace = result.output_dir / "workspace"
            solver_workspace = (
                generation_dir / "solver" if clean_layout else archived_workspace
            )
            if clean_layout:
                if solver_workspace.exists():
                    shutil.rmtree(solver_workspace)
                shutil.move(str(archived_workspace), str(solver_workspace))
                research_summary = result.output_dir / "final_summary.json"
                if research_summary.is_file():
                    research_summary.replace(result.output_dir / "summary.json")

            if research:
                progress = result.summary
                levels, win_levels = int(progress["best_levels_completed"]), int(progress["win_levels"])
                scored = SolverEvaluation(
                    fitness=float(levels),
                    success=0 < win_levels <= levels,
                    terminal=result.task.terminal,
                    score={"research_levels_completed": levels, "actions_to_best": progress["actions_to_best"],
                           "win_levels": win_levels},
                    finish_reason=result.finish_reason,
                    environment_steps=result.environment_steps,
                )
            else:
                solver_loaded = load_profile(
                    self.config.profile, self.config.profile_settings
                )
                scored = evaluate_solver_workspace(
                    loaded_profile=solver_loaded,
                    workspace=solver_workspace,
                    output_dir=evaluation_dir,
                    max_environment_steps=self.config.fresh_solver_max_environment_steps,
                    max_wall_seconds=player.max_wall_seconds,
                )

        research_evaluation = dict(result.summary)
        if clean_layout:
            transcript_name = Path(str(research_evaluation.get("transcript", ""))).name
            if transcript_name:
                research_evaluation["transcript"] = str(
                    solver_workspace / transcript_name
                )
            research_evaluation["output_dir"] = str(research_dir)
            (research_dir / "summary.json").write_text(
                json.dumps(research_evaluation, indent=2), encoding="utf-8"
            )

        combined_score = {
            **dict(scored.score),
            "research_fitness": result.task.fitness,
            "research_score": result.task.score,
            "research_environment_actions": result.environment_steps,
            "research_moves_budget": player.max_environment_steps,
            "research_start_level": start_level,
        }
        final_summary = {
            "candidate_id": candidate.candidate_id,
            "success": scored.success,
            "terminal": scored.terminal,
            "fitness": scored.fitness,
            "score": combined_score,
            "finish_reason": scored.finish_reason,
            "environment_steps": scored.environment_steps,
            "research_evaluation": research_evaluation,
            "research": str(research_dir),
            "solver": str(solver_workspace),
            "solver_evaluation": None if research else str(evaluation_dir),
            "output_dir": str(generation_dir),
        }
        summary_name = "summary.json" if clean_layout else "final_summary.json"
        summary_path = generation_dir / summary_name
        summary_path.write_text(
            json.dumps(final_summary, indent=2), encoding="utf-8"
        )

        return CandidateEvaluation(
            evaluation_id="evaluation" if clean_layout else generation_dir.name,
            candidate_id=candidate.candidate_id,
            fitness=scored.fitness,
            success=scored.success,
            terminal=scored.terminal,
            score=combined_score,
            finish_reason=scored.finish_reason,
            environment_steps=scored.environment_steps,
            agent_turns=result.agent_turns,
            run_dir=generation_dir,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
