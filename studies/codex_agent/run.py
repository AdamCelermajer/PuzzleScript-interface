from __future__ import annotations

import json
import sys
import traceback
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.arc.arcade_env import ArcadeEnv
from client.screen_dashboard import ScreenDashboard

from studies.codex_agent.runner import CodexAgentRunner
from studies.codex_agent.openrouter_session import open_game_session
from studies.codex_agent.session import CodexSessionConfig


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


def _run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _print_event(message: str) -> None:
    safe = str(message).encode("ascii", errors="replace").decode("ascii")
    print(f"[codex] {safe}")


def main() -> None:
    parser = ArgumentParser(
        description="Persistent Codex SDK PuzzleScript agent"
    )
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument(
        "--codex-bin",
        default="",
        help="Optional Codex CLI path. By default the installed Codex app is detected.",
    )
    parser.add_argument(
        "--effort",
        default="low",
        choices=["minimal", "low", "medium", "high", "xhigh", "max"],
        help="Codex SDK reasoning effort. The app's Light setting is low here.",
    )
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--max-decisions", type=int, default=None)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--continue-from", default="", help="Restore an unsolved completed run in a new session; max-steps is the additional budget.")
    parser.add_argument(
        "--condition",
        choices=["baseline", "baseline-plus"],
        default="baseline",
    )
    parser.add_argument(
        "--harness",
        choices=["codex", "tools", "raw"],
        default="codex",
        help="H2 codex (Codex SDK), H1 tools (native tools), H0 raw (text-only tools). H0/H1 use OpenRouter or NanoGPT.",
    )
    parser.add_argument("--provider", default="",
                        help="Pin one OpenRouter provider slug (no fallback), e.g. alibaba or deepinfra.")
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Run headless without the tkinter dashboard.",
    )
    args = parser.parse_args()

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else DEFAULT_OUTPUT_ROOT / _run_id()
    )
    if args.continue_from:
        from studies.codex_agent.continuation import load_parent
        load_parent(args.continue_from)
        parent_config = json.loads((Path(args.continue_from) / "run_config.json").read_text(encoding="utf-8"))
        if any(parent_config[key] != value for key, value in {
            "model": args.model, "reasoning_effort": args.effort,
            "condition": args.condition, "game_id": args.game_id,
        }.items()) or parent_config.get("harness", "codex") != args.harness or parent_config.get("provider", "") != args.provider:
            raise ValueError("Continuation must preserve the parent model, effort, condition, harness, and game")
        if output_dir.resolve() == Path(args.continue_from).resolve() or output_dir.exists():
            raise ValueError("Continuation requires a fresh separate output directory")
    dashboard = None
    event_sink = _print_event
    if not args.no_window:
        dashboard = ScreenDashboard(
            game_id=args.game_id,
            mode="CODEX",
            controls="One persistent Codex SDK session. Close or press Ctrl+C to stop.",
        )
        event_sink = dashboard.push_event

    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
        renderer=dashboard.render if dashboard is not None else None,
    )
    config = CodexSessionConfig(
        model=args.model,
        effort=args.effort,
        codex_bin=args.codex_bin,
        workspace_enabled=(args.condition == "baseline-plus"),
        harness=args.harness,
        provider=args.provider,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "condition": args.condition,
                "harness": args.harness,
                "provider": args.provider,
                "model": args.model,
                "reasoning_effort": args.effort,
                "game_id": args.game_id,
                "backend_url": args.backend_url,
                "max_steps": args.max_steps,
                "max_decisions": args.max_decisions,
                "continuation_from": str(Path(args.continue_from).resolve()) if args.continue_from else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result_holder = {}

    def run_agent() -> None:
        try:
            session_workspace = output_dir / (
                "workspace" if config.workspace_enabled else "codex_workspace"
            )
            if args.continue_from:
                from studies.codex_agent.continuation import seed_notes
                seed_notes(args.continue_from, session_workspace)
            with open_game_session(
                config,
                session_workspace,
                artifact_directory=output_dir,
            ) as session:
                runner = CodexAgentRunner(
                    env=env,
                    session=session,
                    output_dir=output_dir,
                    max_steps=args.max_steps,
                    max_decisions=args.max_decisions,
                    event_sink=event_sink,
                    workspace_enabled=config.workspace_enabled,
                    continuation_from=args.continue_from or None,
                )
                result_holder["result"] = runner.run()
        except BaseException as exc:
            (output_dir / "error.json").write_text(
                json.dumps(
                    {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            raise

    if dashboard is None:
        run_agent()
    else:
        try:
            dashboard.run_engine(run_agent)
        finally:
            dashboard.close()

    result = result_holder.get("result")
    if result is None:
        print("Codex agent run interrupted before completion.")
        print(f"output_dir={output_dir}")
        return

    print(f"solved={result.solved}")
    print(f"status={result.status}")
    print(f"reason={result.reason}")
    print(f"actions={[action.name for action in result.actions]}")
    print(f"decisions={result.decisions}")
    print(f"workspace_operations={result.workspace_operations}")
    print(f"world_model={result.world_model_path}")
    print(f"output_dir={result.output_dir}")
    print(f"transcript={result.transcript_path}")
    print(f"transitions={result.transitions_path}")
    print(f"session_log={output_dir / ('codex_session.jsonl' if args.harness == 'codex' else 'model_session.jsonl')}")


if __name__ == "__main__":
    main()
