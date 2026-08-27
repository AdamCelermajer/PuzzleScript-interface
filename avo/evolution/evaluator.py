from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from avo.core.profile import load_profile
from avo.evolution.candidate import CandidateEvaluation, RunCandidate
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

        return CandidateEvaluation(
            evaluation_id=run_dir.name,
            candidate_id=candidate.candidate_id,
            fitness=result.task.fitness,
            success=result.task.success,
            terminal=result.task.terminal,
            score=result.task.score,
            finish_reason=result.finish_reason,
            environment_steps=result.environment_steps,
            agent_turns=result.agent_turns,
            run_dir=result.output_dir,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
