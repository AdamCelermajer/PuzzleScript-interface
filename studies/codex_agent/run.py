from __future__ import annotations

import sys
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.arc.arcade_env import ArcadeEnv
from client.screen_dashboard import ScreenDashboard

from studies.codex_agent.runner import CodexAgentRunner
from studies.codex_agent.session import CodexGameSession, CodexSessionConfig


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
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help="Codex SDK reasoning effort. The app's Light setting is low here.",
    )
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--max-decisions", type=int, default=None)
    parser.add_argument("--output-dir", default="")
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Run headless without the tkinter dashboard.",
    )
    args = parser.parse_args()

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else DEFAULT_OUTPUT_ROOT / f"{_run_id()}-{args.game_id}"
    )
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
    )
    result_holder = {}

    def run_agent() -> None:
        with CodexGameSession(config, output_dir / "codex_workspace") as session:
            runner = CodexAgentRunner(
                env=env,
                session=session,
                output_dir=output_dir,
                max_steps=args.max_steps,
                max_decisions=args.max_decisions,
                event_sink=event_sink,
            )
            result_holder["result"] = runner.run()

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
    print(f"output_dir={result.output_dir}")
    print(f"transcript={result.transcript_path}")


if __name__ == "__main__":
    main()
