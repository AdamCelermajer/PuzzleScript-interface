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


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output" / "evolution"
OUTER_PROMPT = Path(__file__).resolve().parent / "prompts" / "outer_optimizer.txt"
DEFAULT_SEED_STRATEGY = """Solve the mission autonomously through controlled experiments.
Preserve concrete discoveries in NOTES.md and reusable programs in the workspace.
Use environment evidence rather than assuming action meanings or game rules.
"""


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
    parser.add_argument("--seed-strategy", default="")
    parser.add_argument("--player-base-prompt", default="")
    parser.add_argument("--player-model", default="gpt-5.6-sol")
    parser.add_argument("--player-effort", default="high")
    parser.add_argument("--player-max-environment-steps", type=int, default=300)
    parser.add_argument("--player-max-theory-candidates", type=int, default=10)
    parser.add_argument("--fresh-solver-max-environment-steps", type=int, default=1_500)
    parser.add_argument("--player-max-wall-seconds", type=float, default=3600)
    parser.add_argument("--player-max-agent-turns", type=int, default=4)
    parser.add_argument("--optimizer-model", default="gpt-5.6-sol")
    parser.add_argument("--optimizer-effort", default="high")
    parser.add_argument("--optimizer-max-agent-turns", type=int, default=30)
    parser.add_argument("--max-evaluations", type=int, default=6)
    parser.add_argument("--max-wall-seconds", type=float, default=14_400)
    parser.add_argument("--codex-bin", default="")
    args = parser.parse_args()

    overrides = dict(_setting(item) for item in args.set)
    loaded_for_metadata = load_profile(args.profile, overrides)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    root = Path(args.output_dir or DEFAULT_OUTPUT_ROOT / run_id).resolve()
    optimizer_workspace = root / "outer"
    store = EvolutionStore.create(root, optimizer_workspace)
    if not store.candidates():
        strategy = (
            Path(args.seed_strategy).read_text(encoding="utf-8")
            if args.seed_strategy
            else DEFAULT_SEED_STRATEGY
        )
        store.create_seed("x_0001", strategy)

    player_settings = PlayerRunSettings(
        model=args.player_model,
        effort=args.player_effort,
        codex_bin=args.codex_bin,
        base_prompt=args.player_base_prompt or PlayerRunSettings.base_prompt,
        max_environment_steps=args.player_max_environment_steps,
        max_theory_candidates=args.player_max_theory_candidates,
        max_wall_seconds=args.player_max_wall_seconds,
        max_agent_turns=args.player_max_agent_turns,
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
        budget=EvolutionBudget(
            max_evaluations=args.max_evaluations,
            max_wall_seconds=args.max_wall_seconds,
        ),
    )
    config = {
        "schema_version": 1,
        "profile_id": loaded_for_metadata.implementation.profile_id,
        "profile_manifest": str(loaded_for_metadata.manifest_path),
        "profile_manifest_hash": loaded_for_metadata.manifest_hash,
        "profile_prompt_hash": loaded_for_metadata.prompt_hash,
        "profile_settings": _jsonable(overrides),
        "objective": loaded_for_metadata.implementation.objective,
        "fitness_owner": "fresh solver levels multiplied by prospective model accuracy",
        "player": _jsonable(player_settings),
        "fresh_solver_max_environment_steps": args.fresh_solver_max_environment_steps,
        "optimizer_model": args.optimizer_model,
        "optimizer_effort": args.optimizer_effort,
        "optimizer_max_agent_turns": args.optimizer_max_agent_turns,
        "max_evaluations": args.max_evaluations,
        "max_wall_seconds": args.max_wall_seconds,
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
            codex_bin=args.codex_bin,
            prompt_path=OUTER_PROMPT,
            task_instructions=gateway.mission,
            max_turns=args.optimizer_max_agent_turns,
            analysis_dir=root / "optimizer_analysis",
        )
    )
    result = optimizer.run(
        gateway,
        optimizer_workspace,
        tool_server=tool_server,
    )
    summary = {
        "success": gateway.success,
        "finish_reason": result.finish_reason,
        "optimizer_turns": result.turns,
        "population": store.population_summary(),
        "output_dir": str(root),
    }
    (root / "evolution_summary.json").write_text(
        json.dumps(_jsonable(summary), indent=2),
        encoding="utf-8",
    )
    print(json.dumps(_jsonable(summary), indent=2))


if __name__ == "__main__":
    main()
