from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.core.framework import AvoLaboratory, _jsonable
from avo.core.profile import load_profile
from avo.core.run_store import RunStore
from avo.core.tool_gateway import AvoToolGateway, GatewayBudget


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
    parser.add_argument("--codex-bin", default="")
    parser.add_argument("--max-environment-steps", type=int, default=200)
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--max-wall-seconds", type=float, default=3600)
    parser.add_argument("--max-agent-turns", type=int, default=4)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    overrides = dict(_setting(item) for item in args.set)
    loaded = load_profile(args.profile, overrides)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    store = RunStore.create(
        Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / run_id
    )
    workspace = Path(tempfile.mkdtemp(prefix="avo-agent-run-")).resolve()
    base_prompt_path = Path(args.base_prompt or CodexOAuthConfig.prompt_path).resolve()

    config = {
        "profile_id": loaded.implementation.profile_id,
        "profile_manifest": str(loaded.manifest_path),
        "profile_manifest_hash": loaded.manifest_hash,
        "profile_prompt": str(loaded.prompt_path),
        "profile_prompt_hash": loaded.prompt_hash,
        "profile_settings": _jsonable(loaded.settings),
        "objective": loaded.implementation.objective,
        "agent_backend": "CodexOAuthAgent",
        "model": args.model,
        "effort": args.effort,
        "base_prompt": str(base_prompt_path),
        "base_prompt_hash": hashlib.sha256(base_prompt_path.read_bytes()).hexdigest(),
        "max_environment_steps": args.max_environment_steps,
        "max_candidates": args.max_candidates,
        "max_wall_seconds": args.max_wall_seconds,
        "max_agent_turns": args.max_agent_turns,
        "workspace_isolation": "external temporary directory",
    }
    store.write_json("run_config.json", config)

    profile = loaded.implementation
    laboratory = AvoLaboratory(profile.environment, [], store.root)
    laboratory.store.append(
        "run_started",
        {
            "profile_id": profile.profile_id,
            "objective": profile.objective,
            "profile_manifest_hash": loaded.manifest_hash,
            "profile_prompt_hash": loaded.prompt_hash,
        },
    )
    gateway = AvoToolGateway(
        laboratory,
        profile,
        store.candidates,
        budget=GatewayBudget(
            max_environment_steps=args.max_environment_steps,
            max_candidates=args.max_candidates,
            max_wall_seconds=args.max_wall_seconds,
        ),
    )
    agent_config = CodexOAuthConfig(
        model=args.model,
        effort=args.effort,
        codex_bin=args.codex_bin,
        prompt_path=base_prompt_path,
        task_instructions=loaded.prompt,
        max_turns=args.max_agent_turns,
        analysis_dir=store.root / "analysis",
    )
    result = CodexOAuthAgent(agent_config).run(gateway, workspace)
    store.archive_agent_workspace(workspace)

    current = laboratory.current
    if current is None:
        raise RuntimeError("AVO run ended before the environment was initialized")
    task = profile.evaluate(tuple(laboratory.history), current)
    summary = {
        "success": task.success,
        "terminal": task.terminal,
        "score": _jsonable(task.score),
        "finish_reason": result.finish_reason,
        "agent_turns": result.turns,
        "environment_steps": gateway.environment_steps,
        "candidates": len(laboratory.candidates),
        "final_status": current.status,
        "transcript": str(store.root / "workspace" / result.transcript_path.name),
        "evidence": str(store.evidence_file),
        "analysis": str(store.root / "analysis"),
        "output_dir": str(store.root),
    }
    store.write_json("final_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
