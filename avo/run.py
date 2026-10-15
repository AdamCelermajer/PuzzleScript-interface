from __future__ import annotations

import json
import sys
import tempfile
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from avo.core.profile import load_profile
from avo.run_once import PlayerRunSettings, execute_player_run
from avo.isolation import new_workspace


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


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
    parser = ArgumentParser(description="Run the self-contained AVO framework")
    parser.add_argument(
        "--profile",
        default="puzzlescript",
        help="Bundled profile ID or path to profile.toml",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override one environment profile setting; may be repeated",
    )
    parser.add_argument("--base-prompt", default="")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--harness", default="codex",
                        choices=("codex", "claude-code", "opencode", "antigravity", "bare"))
    parser.add_argument("--provider", default="")
    parser.add_argument("--max-environment-steps", type=int, default=200)
    parser.add_argument("--max-wall-seconds", type=float, default=3600)
    parser.add_argument("--max-agent-turns", type=int, default=4)
    parser.add_argument("--max-solver-self-checks", type=int, default=2)
    parser.add_argument("--solver-self-check-max-environment-steps", type=int, default=1_500)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    overrides = dict(_setting(item) for item in args.set)
    loaded = load_profile(args.profile, overrides)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / run_id
    workspace = new_workspace()
    result = execute_player_run(
        loaded_profile=loaded,
        output_dir=output_dir,
        workspace=workspace,
        settings=PlayerRunSettings(
            model=args.model,
            effort=args.effort,
            harness=args.harness,
            provider=args.provider,
            base_prompt=args.base_prompt or PlayerRunSettings.base_prompt,
            max_environment_steps=args.max_environment_steps,
            max_wall_seconds=args.max_wall_seconds,
            max_agent_turns=args.max_agent_turns,
            max_solver_self_checks=args.max_solver_self_checks,
            solver_self_check_max_environment_steps=(
                args.solver_self_check_max_environment_steps
            ),
        ),
    )
    print(json.dumps(result.summary, indent=2))


if __name__ == "__main__":
    main()
