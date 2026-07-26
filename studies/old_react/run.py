from __future__ import annotations

import sys
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.arc.arcade_env import ArcadeEnv
from client.screen_dashboard import ScreenDashboard

from studies.old_react.llm_client import ReactLlmClient, ReactLlmConfig
from studies.old_react.runner import ReactAgentRunner


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


def _run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _print_event(message: str) -> None:
    safe = str(message).encode("ascii", errors="replace").decode("ascii")
    print(f"[old-react] {safe}")


def main() -> None:
    parser = ArgumentParser(description="Archived experimental ReAct PuzzleScript agent")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument(
        "--model",
        default="kimi-k2.6",
        help="Moonshot/Kimi model id to use for the archived ReAct agent.",
    )
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--max-tool-calls", type=int, default=None)
    parser.add_argument("--max-llm-errors", type=int, default=3)
    parser.add_argument(
        "--max-non-action-tools",
        type=int,
        default=2,
        help="How many inspect/read/write/run tools may happen before an action is required.",
    )
    parser.add_argument(
        "--max-probe-actions",
        type=int,
        default=0,
        help="Fresh-episode action budget for generic probe_action_tree.",
    )
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
    cfg = ReactLlmConfig(
        model=args.model,
    )
    result_holder = {}
    dashboard = None
    event_sink = None
    if not args.no_window:
        dashboard = ScreenDashboard(
            game_id=args.game_id,
            mode="OLD REACT",
            controls="Archived ReAct agent dashboard. Close or press Ctrl+C to stop.",
        )
        event_sink = dashboard.push_event
    else:
        event_sink = _print_event

    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
        renderer=dashboard.render if dashboard is not None else None,
    )
    llm = ReactLlmClient(
        cfg,
        event_sink=dashboard.push_event if dashboard is not None else None,
    )
    runner = ReactAgentRunner(
        env=env,
        llm_client=llm,
        output_dir=output_dir,
        max_steps=args.max_steps,
        max_tool_calls=args.max_tool_calls,
        max_llm_errors=args.max_llm_errors,
        max_non_action_tools=args.max_non_action_tools,
        max_probe_actions=args.max_probe_actions,
        probe_env_factory=lambda: ArcadeEnv(
            game_id=args.game_id,
            backend_url=args.backend_url,
        ),
        event_sink=event_sink,
    )

    def run_agent() -> None:
        result_holder["result"] = runner.run()

    if dashboard is None:
        result_holder["result"] = runner.run()
    else:
        try:
            dashboard.run_engine(run_agent)
        finally:
            dashboard.close()

    result = result_holder.get("result")
    if result is None:
        print("Old ReAct agent run interrupted before completion.")
        print(f"output_dir={output_dir}")
        return

    print(f"solved={result.solved}")
    print(f"actions={[action.name for action in result.actions]}")
    print(f"output_dir={result.output_dir}")
    print(f"transcript={result.transcript_path}")


if __name__ == "__main__":
    main()
