from __future__ import annotations

import json
import shutil
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from avo.core.profile import load_profile
from avo.evolution.candidate import CandidateEvaluation, RunCandidate
from avo.evolution.solver_evaluation import evaluate_solver_workspace
from avo.run_once import PlayerRunSettings, execute_player_run
from avo.isolation import new_workspace


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


class CandidateEvaluator:
    """Trusted evaluation of a complete run candidate in a fresh environment."""

    def __init__(self, config: PlayerEvaluationConfig) -> None:
        self.config = config

    def evaluate(
        self,
        candidate: RunCandidate,
        run_dir: Path,
    ) -> CandidateEvaluation:
        # Loading here, rather than in __init__, constructs a fresh profile/environment
        # for every x_i.
        loaded = load_profile(self.config.profile, self.config.profile_settings)
        generation_dir = run_dir.resolve()
        clean_layout = generation_dir == candidate.root.resolve()
        research_dir = generation_dir / "research" if clean_layout else generation_dir
        evaluation_dir = (
            generation_dir / "evaluation"
            if clean_layout
            else generation_dir / "solver_evaluation"
        )
        research_dir.mkdir(parents=True, exist_ok=True)
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        # Opaque external directory, retained to avoid restricted-token ACL
        # cleanup hangs. Never inherit the repository's AGENTS/config chain.
        with nullcontext(new_workspace()) as raw:
            workspace = Path(raw).resolve()
            if candidate.workspace_path.is_dir():
                shutil.copytree(candidate.workspace_path, workspace, dirs_exist_ok=True)
            result = execute_player_run(
                loaded_profile=loaded,
                output_dir=research_dir,
                workspace=workspace,
                settings=self.config.player,
                candidate_id=candidate.candidate_id,
                candidate_strategy=candidate.strategy(),
                run_metadata={"parent_ids": list(candidate.parent_ids)},
            )

            # The researching Codex player's progress is evidence, not fitness.
            # Reloading the profile creates a second fresh game in which only the
            # archived solver may act. Only progress in this fresh game owns fitness.
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

            solver_loaded = load_profile(
                self.config.profile, self.config.profile_settings
            )
            solver_result = evaluate_solver_workspace(
                loaded_profile=solver_loaded,
                workspace=solver_workspace,
                output_dir=evaluation_dir,
                max_environment_steps=self.config.fresh_solver_max_environment_steps,
                max_wall_seconds=self.config.player.max_wall_seconds,
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
            **dict(solver_result.score),
            "research_fitness": result.task.fitness,
            "research_score": result.task.score,
            "research_environment_actions": result.environment_steps,
        }
        final_summary = {
            "candidate_id": candidate.candidate_id,
            "success": solver_result.success,
            "terminal": solver_result.terminal,
            "fitness": solver_result.fitness,
            "score": combined_score,
            "finish_reason": solver_result.finish_reason,
            "environment_steps": solver_result.environment_steps,
            "research_evaluation": research_evaluation,
            "research": str(research_dir),
            "solver": str(solver_workspace),
            "solver_evaluation": str(evaluation_dir),
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
            fitness=solver_result.fitness,
            success=solver_result.success,
            terminal=solver_result.terminal,
            score=combined_score,
            finish_reason=solver_result.finish_reason,
            environment_steps=solver_result.environment_steps,
            agent_turns=result.agent_turns,
            run_dir=generation_dir,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
