from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from frameworks.avo import research_score
from frameworks.avo.client.turns import DEFAULT_PROMPT_PATH, RESEARCH_RUN_INSTRUCTION, AgentConfig, CliAgent
from frameworks.avo.core.framework import AvoLaboratory, JsonValue, _jsonable
from frameworks.avo.core.profile import LoadedProfile, TaskEvaluation, load_profile
from frameworks.avo.core.run_store import RunStore
from frameworks.avo.core.tool_gateway import AvoToolGateway, GatewayBudget
from frameworks import world_model


@dataclass(frozen=True)
class PlayerRunSettings:
    model: str = "gpt-5.6-sol"
    effort: str = "high"
    base_prompt: str | Path = DEFAULT_PROMPT_PATH
    max_environment_steps: int = 200
    max_wall_seconds: float = 3600
    max_agent_turns: int = 4
    max_solver_self_checks: int = 2
    solver_self_check_max_environment_steps: int = 1_500
    harness: str = "codex"
    provider: str = ""
    # "research": no solver; the session's own levels are the score (frameworks/avo/research_score.py).
    fitness: str = "solver"
    # AVO3: after the attempt, one last turn asks for world_model.md (copied to world_model_snapshots/final.md).
    final_world_model: bool = False


@dataclass(frozen=True)
class PlayerRunResult:
    task: TaskEvaluation
    finish_reason: str
    agent_turns: int
    environment_steps: int
    output_dir: Path
    summary: Mapping[str, JsonValue]


def execute_player_run(
    *,
    loaded_profile: LoadedProfile,
    output_dir: str | Path,
    workspace: str | Path,
    settings: PlayerRunSettings,
    candidate_id: str | None = None,
    candidate_strategy: str = "",
    run_metadata: Mapping[str, Any] | None = None,
) -> PlayerRunResult:
    """Execute one isolated player run and persist its trusted artifacts."""

    store = RunStore.create(output_dir)
    research = settings.fitness == "research"
    if research:  # the research objective and task prompt
        loaded_profile = research_score.research_profile(loaded_profile)
    workspace_path = Path(workspace).resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    base_prompt_path = Path(settings.base_prompt).resolve()

    config: dict[str, Any] = {
        "profile_id": loaded_profile.implementation.profile_id,
        "profile_manifest": str(loaded_profile.manifest_path),
        "profile_manifest_hash": loaded_profile.manifest_hash,
        "profile_prompt": str(loaded_profile.prompt_path),
        "profile_prompt_hash": loaded_profile.prompt_hash,
        "profile_settings": _jsonable(loaded_profile.settings),
        "objective": loaded_profile.implementation.objective,
        "fitness": settings.fitness,
        "agent_backend": "CliAgent",
        "harness": settings.harness,
        "provider": settings.provider,
        "model": settings.model,
        "effort": settings.effort,
        "base_prompt": str(base_prompt_path),
        "base_prompt_hash": hashlib.sha256(base_prompt_path.read_bytes()).hexdigest(),
        "max_environment_steps": settings.max_environment_steps,
        "max_wall_seconds": settings.max_wall_seconds,
        "max_agent_turns": settings.max_agent_turns,
        "max_solver_self_checks": settings.max_solver_self_checks,
        "solver_self_check_max_environment_steps": (
            settings.solver_self_check_max_environment_steps
        ),
        "workspace_isolation": "temporary directory in the run's Docker container",
    }
    if candidate_id is not None:
        config["run_candidate_id"] = candidate_id
        config["candidate_strategy_hash"] = hashlib.sha256(
            candidate_strategy.encode("utf-8")
        ).hexdigest()
    if run_metadata:
        config["run_metadata"] = _jsonable(run_metadata)
    store.write_json("run_config.json", config)

    profile = loaded_profile.implementation
    laboratory = AvoLaboratory(profile.environment, [], store.root)
    laboratory.store.append(
        "run_started",
        {
            "profile_id": profile.profile_id,
            "objective": profile.objective,
            "profile_manifest_hash": loaded_profile.manifest_hash,
            "profile_prompt_hash": loaded_profile.prompt_hash,
            "run_candidate_id": candidate_id,
        },
    )
    def self_check(check_number: int, max_actions: int) -> Mapping[str, Any]:
        from frameworks.avo.evolution.solver_evaluation import evaluate_solver_workspace

        check_dir = store.root / "self_check" / f"check_{check_number:02d}"
        # A research session that started at a later level (continue_levels) still checks its solver from level 1.
        fresh_profile = load_profile(
            loaded_profile.manifest_path,
            {key: value for key, value in loaded_profile.settings.items() if key != "start_level"},
        )
        result = evaluate_solver_workspace(
            loaded_profile=fresh_profile,
            workspace=workspace_path,
            output_dir=check_dir,
            max_environment_steps=max_actions,
            max_wall_seconds=settings.max_wall_seconds,
        )
        # The inner player may use the scalar as a regression signal, but the
        # evaluator trajectory remains framework-owned. Full artifacts stay in
        # check_dir for trusted outer-loop inspection after the run.
        return {"fitness": result.fitness}

    # The research session keeps world_model.md in its workspace; copies go to <run>/world_model_snapshots/.
    snapshots = world_model.Snapshots(workspace_path / world_model.NAME, store.root)
    gateway = AvoToolGateway(
        laboratory,
        profile,
        budget=GatewayBudget(
            max_environment_steps=settings.max_environment_steps,
            max_wall_seconds=settings.max_wall_seconds,
        ),
        solver_self_check=None if research else self_check,
        max_solver_self_checks=settings.max_solver_self_checks,
        max_solver_self_check_steps=settings.solver_self_check_max_environment_steps,
        on_step=snapshots.after_action,
        solver=not research,
        final_report=("This attempt's game session has ended; do not take more game actions. "
                      + world_model.final_prompt()) if settings.final_world_model else None,
    )

    instructions = [loaded_profile.prompt, world_model.keep_instruction()]
    if candidate_strategy.strip():
        instructions.append(
            "# Run candidate strategy\n\n"
            "This strategy is part of the candidate being evaluated. Follow it when useful, "
            "but trust real environment evidence over unsupported claims.\n\n"
            + candidate_strategy.strip()
        )
    agent_config = AgentConfig(
        model=settings.model,
        effort=settings.effort,
        prompt_path=base_prompt_path,
        task_instructions="\n\n".join(instructions),
        max_turns=settings.max_agent_turns,
        analysis_dir=store.root / "analysis",
        session_role="inner_player",
        harness=settings.harness,
        provider=settings.provider,
        first_instruction=RESEARCH_RUN_INSTRUCTION if research else "",
        session_metadata={
            "candidate_id": candidate_id,
            "profile_id": loaded_profile.implementation.profile_id,
            "run_metadata": _jsonable(run_metadata or {}),
        },
    )
    agent = CliAgent(agent_config)
    agent_result = agent.run(gateway, workspace_path)
    snapshots.final()
    store.archive_agent_workspace(workspace_path)

    current = laboratory.current
    if current is None:
        raise RuntimeError("AVO run ended before the environment was initialized")
    task = profile.evaluate(tuple(laboratory.history), current)
    summary: dict[str, JsonValue] = {
        "candidate_id": candidate_id,
        "success": task.success,
        "terminal": task.terminal,
        "fitness": task.fitness,
        "score": _jsonable(task.score),
        "finish_reason": agent_result.finish_reason,
        "agent_turns": agent_result.turns,
        "environment_steps": gateway.environment_steps,
        "solver_self_checks": _jsonable(gateway.self_checks),
        "final_status": current.status,
        "transcript": str(store.root / "workspace" / agent_result.transcript_path.name),
        "evidence": str(store.evidence_file),
        "analysis": str(store.root / "analysis"),
        "session_manifest": str(store.root / "analysis" / "session.json"),
        "agent_events": str(store.root / "analysis" / "agent_events.jsonl"),
        "output_dir": str(store.root),
    }
    # The research score's fitness, and where a continue_levels campaign's next session starts.
    summary.update(research_score.best_progress(laboratory.history))
    store.write_json("final_summary.json", summary)
    return PlayerRunResult(
        task=task,
        finish_reason=agent_result.finish_reason,
        agent_turns=agent_result.turns,
        environment_steps=gateway.environment_steps,
        output_dir=store.root,
        summary=summary,
    )
