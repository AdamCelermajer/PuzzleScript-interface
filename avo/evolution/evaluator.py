from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from avo.core.profile import load_profile
from avo.evolution.candidate import CandidateEvaluation, RunCandidate
from avo.evolution.solver_evaluation import evaluate_solver_workspace
from avo.run_once import PlayerRunSettings, execute_player_run


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
        run_dir.mkdir(parents=True, exist_ok=True)
        # Keep the sandbox workspace beneath the run directory. On Windows, files
        # created by the restricted Codex token under the system temp directory can
        # receive ACLs that the trusted file-RPC server cannot read.
        with tempfile.TemporaryDirectory(
            prefix=f"avo-player-{candidate.candidate_id}-",
            dir=run_dir,
        ) as raw:
            workspace = Path(raw).resolve()
            if candidate.workspace_path.is_dir():
                shutil.copytree(candidate.workspace_path, workspace, dirs_exist_ok=True)
            result = execute_player_run(
                loaded_profile=loaded,
                output_dir=run_dir,
                workspace=workspace,
                settings=self.config.player,
                candidate_id=candidate.candidate_id,
                candidate_strategy=candidate.strategy(),
                run_metadata={"parent_ids": list(candidate.parent_ids)},
            )

            # The researching Codex player's progress is evidence, not fitness.
            # Reloading the profile creates a second fresh game in which only the
            # archived solver may act. Its model is scored prospectively before
            # every action it executes.
            solver_loaded = load_profile(
                self.config.profile, self.config.profile_settings
            )
            solver_result = evaluate_solver_workspace(
                loaded_profile=solver_loaded,
                workspace=workspace,
                output_dir=run_dir / "solver_evaluation",
                max_environment_steps=self.config.player.max_environment_steps,
                max_wall_seconds=self.config.player.max_wall_seconds,
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
            "research_evaluation": result.summary,
            "solver_evaluation": str(run_dir / "solver_evaluation"),
            "output_dir": str(run_dir),
        }
        (run_dir / "final_summary.json").write_text(
            json.dumps(final_summary, indent=2), encoding="utf-8"
        )

        return CandidateEvaluation(
            evaluation_id=run_dir.name,
            candidate_id=candidate.candidate_id,
            fitness=solver_result.fitness,
            success=solver_result.success,
            terminal=solver_result.terminal,
            score=combined_score,
            finish_reason=solver_result.finish_reason,
            environment_steps=solver_result.environment_steps,
            agent_turns=result.agent_turns,
            run_dir=result.output_dir,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
