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
    # continue_levels: each research session starts at the level where the previous one stopped (frameworks/levels.py);
    # this file records that level across evaluations and resumes.
    level_progress: Path | None = None


def research_start_level(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 1
    return int(json.loads(path.read_text(encoding="utf-8")).get("next_start_level", 1))


class CandidateEvaluator:
    """Trusted evaluation of a complete run candidate: its research session in a fresh environment is the score."""

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
        generation_dir = run_dir.resolve()
        clean_layout = generation_dir == candidate.root.resolve()
        research_dir = generation_dir / "research" if clean_layout else generation_dir
        research_dir.mkdir(parents=True, exist_ok=True)
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

            # The final workspace goes to solver/ (its historical name), which children inherit.
            archived_workspace = result.output_dir / "workspace"
            final_workspace = (
                generation_dir / "solver" if clean_layout else archived_workspace
            )
            if clean_layout:
                if final_workspace.exists():
                    shutil.rmtree(final_workspace)
                shutil.move(str(archived_workspace), str(final_workspace))
                research_summary = result.output_dir / "final_summary.json"
                if research_summary.is_file():
                    research_summary.replace(result.output_dir / "summary.json")

        # The score is the most levels the research session completed (frameworks/avo/research_score.py).
        levels, win_levels = int(result.summary["best_levels_completed"]), int(result.summary["win_levels"])
        fitness, success = float(levels), 0 < win_levels <= levels

        research_evaluation = dict(result.summary)
        if clean_layout:
            transcript_name = Path(str(research_evaluation.get("transcript", ""))).name
            if transcript_name:
                research_evaluation["transcript"] = str(
                    final_workspace / transcript_name
                )
            research_evaluation["output_dir"] = str(research_dir)
            (research_dir / "summary.json").write_text(
                json.dumps(research_evaluation, indent=2), encoding="utf-8"
            )

        combined_score = {
            "research_levels_completed": levels,
            "actions_to_best": result.summary["actions_to_best"],
            "win_levels": win_levels,
            "research_fitness": result.task.fitness,
            "research_score": result.task.score,
            "research_environment_actions": result.environment_steps,
            "research_moves_budget": player.max_environment_steps,
            "research_start_level": start_level,
        }
        final_summary = {
            "candidate_id": candidate.candidate_id,
            "success": success,
            "terminal": result.task.terminal,
            "fitness": fitness,
            "score": combined_score,
            "finish_reason": result.finish_reason,
            "environment_steps": result.environment_steps,
            "research_evaluation": research_evaluation,
            "research": str(research_dir),
            "solver": str(final_workspace),
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
            fitness=fitness,
            success=success,
            terminal=result.task.terminal,
            score=combined_score,
            finish_reason=result.finish_reason,
            environment_steps=result.environment_steps,
            agent_turns=result.agent_turns,
            run_dir=generation_dir,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
