from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.core.framework import _jsonable
from avo.core.profile import load_profile
from avo.evolution.evaluator import CandidateEvaluator, PlayerEvaluationConfig
from avo.evolution.gateway import EvolutionBudget, EvolutionGateway
from avo.evolution.store import EvolutionStore
from avo.evolution.tool_server import EvolutionFileToolServer
from avo.run_once import PlayerRunSettings
from avo.isolation import ISOLATION_VERSION, IsolationError, new_workspace


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output" / "evolution"
OUTER_PROMPT = Path(__file__).resolve().parent / "prompts" / "outer_optimizer.txt"


def _setting(raw: str) -> tuple[str, Any]:
    key, separator, value = raw.partition("=")
    if not separator or not key.strip():
        raise ValueError("--set requires KEY=VALUE")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    return key.strip(), parsed


def main() -> None:
    parser = ArgumentParser(description="Run outer AVO search over whole player runs")
    parser.add_argument("--profile", default="puzzlescript")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--resume-saved-campaign", action="store_true",
                        help="Explicitly continue saved lineage using a fresh isolated optimizer session")
    parser.add_argument("--seed-strategy", default="")
    parser.add_argument("--player-base-prompt", default="")
    parser.add_argument("--player-model", default="gpt-5.3-codex-spark")
    parser.add_argument("--player-effort", default="high")
    parser.add_argument("--player-service-tier", default="")
    parser.add_argument("--player-max-environment-steps", type=int, default=500)
    parser.add_argument("--fresh-solver-max-environment-steps", type=int, default=1_500)
    parser.add_argument("--player-max-wall-seconds", type=float, default=3600)
    parser.add_argument("--player-max-agent-turns", type=int, default=4)
    parser.add_argument("--player-max-solver-self-checks", type=int, default=2)
    parser.add_argument(
        "--solver-self-check-max-environment-steps", type=int, default=1_500
    )
    parser.add_argument("--optimizer-model", default="gpt-5.6-sol")
    parser.add_argument("--optimizer-effort", default="high")
    parser.add_argument("--optimizer-service-tier", default="")
    parser.add_argument("--optimizer-max-agent-turns", type=int, default=30)
    parser.add_argument("--max-evaluations", type=int, default=10)
    parser.add_argument("--max-wall-seconds", type=float, default=14_400)
    parser.add_argument("--world-model-mode", choices=("off", "final-only", "between-hypotheses"), default=None)
    parser.add_argument("--codex-bin", default="")
    args = parser.parse_args()

    overrides = dict(_setting(item) for item in args.set)
    loaded_for_metadata = load_profile(args.profile, overrides)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    root = Path(args.output_dir or DEFAULT_OUTPUT_ROOT / run_id).resolve()
    # A clean campaign must not inherit pre-fix notes/solvers or existing state.
    if not args.resume_saved_campaign and ((root / "lineage.json").exists() or (root / "evolution_config.json").exists()):
        raise IsolationError("Use a fresh output directory for an isolated campaign; automatic resume is disabled")
    optimizer_workspace = new_workspace()
    store = EvolutionStore.create(root, optimizer_workspace)
    if args.resume_saved_campaign:
        saved = json.loads((root / "evolution_config.json").read_text(encoding="utf-8"))
        if args.world_model_mode is None:
            args.world_model_mode = saved.get("world_model_mode", "off")
        if saved.get("world_model_mode", "off") != args.world_model_mode:
            raise ValueError("Cannot change world-model condition while continuing a campaign")
    elif args.world_model_mode is None:
        args.world_model_mode = "final-only"
    initial_path = root / "initial_observation.json"
    if initial_path.is_file():
        initial_observation = json.loads(initial_path.read_text(encoding="utf-8"))
    else:
        configure_rendered_frames = getattr(
            loaded_for_metadata.implementation.environment,
            "set_rendered_frame_output_dir",
            None,
        )
        if callable(configure_rendered_frames):
            configure_rendered_frames(root / "initial_frames")
        initial_observation = _jsonable(
            loaded_for_metadata.implementation.environment.reset()
        )
        initial_path.write_text(
            json.dumps(initial_observation, indent=2), encoding="utf-8"
        )
    if not store.candidates() and not (store.drafts_dir / "x_0001").exists():
        strategy = (
            Path(args.seed_strategy).read_text(encoding="utf-8")
            if args.seed_strategy
            else ""
        )
        store.prepare_seed_draft("x_0001", strategy)

    player_settings = PlayerRunSettings(
        model=args.player_model,
        effort=args.player_effort,
        service_tier=args.player_service_tier,
        codex_bin=args.codex_bin,
        base_prompt=args.player_base_prompt or PlayerRunSettings.base_prompt,
        max_environment_steps=args.player_max_environment_steps,
        max_wall_seconds=args.player_max_wall_seconds,
        max_agent_turns=args.player_max_agent_turns,
        max_solver_self_checks=args.player_max_solver_self_checks,
        solver_self_check_max_environment_steps=(
            args.solver_self_check_max_environment_steps
        ),
    )
    evaluator = CandidateEvaluator(
        PlayerEvaluationConfig(
            profile=args.profile,
            profile_settings=overrides,
            player=player_settings,
            fresh_solver_max_environment_steps=args.fresh_solver_max_environment_steps,
        )
    )
    gateway = EvolutionGateway(
        store,
        evaluator,
        mission=(
            f"Improve complete player-agent candidates for profile "
            f"{loaded_for_metadata.implementation.profile_id!r}.\n\n"
            f"Environment objective: {loaded_for_metadata.implementation.objective}\n\n"
            f"The fixed evaluator allows {args.max_evaluations} candidate evaluations."
        ),
        initial_observation=initial_observation,
        budget=EvolutionBudget(
            max_evaluations=args.max_evaluations,
            max_wall_seconds=args.max_wall_seconds,
        ),
        world_model_mode=args.world_model_mode,
    )
    if args.world_model_mode == "between-hypotheses":
        gateway.mission += (
            "\n\nBetween hypotheses, update drafts/CANDIDATE_ID/seed/world_model.md "
            "with your current understanding of the game's rules for the next inner session."
        )
    config = {
        "schema_version": 1,
        "isolation_version": ISOLATION_VERSION,
        "optimizer_workspace": str(optimizer_workspace),
        "profile_id": loaded_for_metadata.implementation.profile_id,
        "profile_manifest": str(loaded_for_metadata.manifest_path),
        "profile_manifest_hash": loaded_for_metadata.manifest_hash,
        "profile_prompt_hash": loaded_for_metadata.prompt_hash,
        "profile_settings": _jsonable(overrides),
        "objective": loaded_for_metadata.implementation.objective,
        "initial_observation": str(initial_path),
        "fitness_owner": "fresh solver levels completed",
        "player": _jsonable(player_settings),
        "fresh_solver_max_environment_steps": args.fresh_solver_max_environment_steps,
        "optimizer_model": args.optimizer_model,
        "optimizer_effort": args.optimizer_effort,
        "optimizer_service_tier": args.optimizer_service_tier,
        "optimizer_max_agent_turns": args.optimizer_max_agent_turns,
        "max_evaluations": args.max_evaluations,
        "max_wall_seconds": args.max_wall_seconds,
        "world_model_mode": args.world_model_mode,
    }
    (root / "evolution_config.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    tool_server = EvolutionFileToolServer(gateway, optimizer_workspace)
    optimizer = CodexOAuthAgent(
        CodexOAuthConfig(
            model=args.optimizer_model,
            effort=args.optimizer_effort,
            service_tier=args.optimizer_service_tier,
            codex_bin=args.codex_bin,
            prompt_path=OUTER_PROMPT,
            task_instructions=gateway.mission,
            max_turns=args.optimizer_max_agent_turns,
            analysis_dir=root / "optimizer_analysis",
            session_role="outer_optimizer",
            session_metadata={
                "profile_id": loaded_for_metadata.implementation.profile_id,
                "run_kind": "evolution",
            },
        )
    )
    result = optimizer.run(
        gateway,
        optimizer_workspace,
        tool_server=tool_server,
    )
    # Archive the outer's report separately from the immutable evaluated solver.
    report = optimizer_workspace / "world_model.md"
    report_present = report.is_file() and not report.is_symlink() and bool(report.read_text(encoding="utf-8").strip())
    if report_present:
        (root / "world_model.md").write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    report_record = {
        "mode": args.world_model_mode, "author": "outer_optimizer",
        "status": "available" if report_present else "missing",
        "final_call_requested": gateway._final_report_requested,
        "best_evaluation": store.population_summary()["best"],
    }
    (root / "world_model.json").write_text(json.dumps(_jsonable(report_record), indent=2), encoding="utf-8")
    summary = {
        "success": gateway.success,
        "finish_reason": result.finish_reason,
        "optimizer_turns": result.turns,
        "population": store.population_summary(),
        "optimizer_session_manifest": str(root / "optimizer_analysis" / "session.json"),
        "output_dir": str(root),
        "world_model": report_record,
    }
    (root / "evolution_summary.json").write_text(
        json.dumps(_jsonable(summary), indent=2),
        encoding="utf-8",
    )
    print(json.dumps(_jsonable(summary), indent=2))


if __name__ == "__main__":
    main()
