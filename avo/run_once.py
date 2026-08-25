from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.core.framework import AvoLaboratory, JsonValue, _jsonable
from avo.core.profile import LoadedProfile, TaskEvaluation
from avo.core.run_store import RunStore
from avo.core.tool_gateway import AvoToolGateway, GatewayBudget


@dataclass(frozen=True)
class PlayerRunSettings:
    model: str = "gpt-5.6-sol"
    effort: str = "high"
    codex_bin: str = ""
    base_prompt: str | Path = CodexOAuthConfig.prompt_path
    max_environment_steps: int = 200
    max_theory_candidates: int = 50
    max_wall_seconds: float = 3600
    max_agent_turns: int = 4


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
        "max_candidates": settings.max_theory_candidates,
        "max_wall_seconds": settings.max_wall_seconds,
        "max_agent_turns": settings.max_agent_turns,
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
    gateway = AvoToolGateway(
        laboratory,
        profile,
        store.candidates,
        budget=GatewayBudget(
            max_environment_steps=settings.max_environment_steps,
            max_candidates=settings.max_theory_candidates,
            max_wall_seconds=settings.max_wall_seconds,
        ),
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
        codex_bin=settings.codex_bin,
        prompt_path=base_prompt_path,
        task_instructions="\n\n".join(instructions),
        max_turns=settings.max_agent_turns,
        analysis_dir=store.root / "analysis",
    )
    agent_result = CodexOAuthAgent(agent_config).run(gateway, workspace_path)
    store.archive_agent_workspace(workspace_path)

    current = laboratory.current
    if current is None:
        raise RuntimeError("AVO run ended before the environment was initialized")
    task = profile.evaluate(tuple(laboratory.history), current)
    summary = {
        "candidate_id": candidate_id,
        "success": task.success,
        "terminal": task.terminal,
        "fitness": task.fitness,
        "score": _jsonable(task.score),
        "finish_reason": agent_result.finish_reason,
        "agent_turns": agent_result.turns,
        "environment_steps": gateway.environment_steps,
        "candidates": len(laboratory.candidates),
        "theory_candidates": len(laboratory.candidates),
        "final_status": current.status,
        "transcript": str(store.root / "workspace" / agent_result.transcript_path.name),
        "evidence": str(store.evidence_file),
        "analysis": str(store.root / "analysis"),
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
