from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.core.framework import AvoLaboratory, JsonValue, _jsonable
from avo.core.profile import LoadedProfile, TaskEvaluation, load_profile
from avo.core.run_store import RunStore
from avo.core.tool_gateway import AvoToolGateway, GatewayBudget


@dataclass(frozen=True)
class PlayerRunSettings:
    model: str = "gpt-5.6-sol"
    effort: str = "high"
    service_tier: str = ""
    codex_bin: str = ""
    base_prompt: str | Path = CodexOAuthConfig.prompt_path
    max_environment_steps: int = 200
    max_wall_seconds: float = 3600
    max_agent_turns: int = 4
    max_solver_self_checks: int = 2
    solver_self_check_max_environment_steps: int = 1_500


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
        "agent_backend": "CodexOAuthAgent",
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
        "workspace_isolation": "external temporary directory",
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
        from avo.evolution.solver_evaluation import evaluate_solver_workspace

        check_dir = store.root / "self_check" / f"check_{check_number:02d}"
        fresh_profile = load_profile(
            loaded_profile.manifest_path,
            loaded_profile.settings,
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

    gateway = AvoToolGateway(
        laboratory,
        profile,
        budget=GatewayBudget(
            max_environment_steps=settings.max_environment_steps,
            max_wall_seconds=settings.max_wall_seconds,
        ),
        solver_self_check=self_check,
        max_solver_self_checks=settings.max_solver_self_checks,
        max_solver_self_check_steps=settings.solver_self_check_max_environment_steps,
    )

    instructions = [loaded_profile.prompt]
    if candidate_strategy.strip():
        instructions.append(
            "# Run candidate strategy\n\n"
            "This strategy is part of the candidate being evaluated. Follow it when useful, "
            "but trust real environment evidence over unsupported claims.\n\n"
            + candidate_strategy.strip()
        )
    agent_config = CodexOAuthConfig(
        model=settings.model,
        effort=settings.effort,
        service_tier=settings.service_tier,
        codex_bin=settings.codex_bin,
        prompt_path=base_prompt_path,
        task_instructions="\n\n".join(instructions),
        max_turns=settings.max_agent_turns,
        analysis_dir=store.root / "analysis",
        session_role="inner_player",
        session_metadata={
            "candidate_id": candidate_id,
            "profile_id": loaded_profile.implementation.profile_id,
            "run_metadata": _jsonable(run_metadata or {}),
        },
    )
    agent_result = CodexOAuthAgent(agent_config).run(gateway, workspace_path)
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
        "output_dir": str(store.root),
    }
    store.write_json("final_summary.json", summary)
    return PlayerRunResult(
        task=task,
        finish_reason=agent_result.finish_reason,
        agent_turns=agent_result.turns,
        environment_steps=gateway.environment_steps,
        output_dir=store.root,
        summary=summary,
    )
