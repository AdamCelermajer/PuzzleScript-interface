from __future__ import annotations

import json
import sys
import tempfile
import time
import traceback
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.arc.arcade_env import ArcadeEnv

from harnesses.registry import HARNESS_IDS
from frameworks.baseline.runner import CodexAgentRunner
from frameworks.baseline.session import CliGameSession, GameSessionConfig

# Recorded harness names of runs launched before the harnesses package.
LEGACY_HARNESS = {"tools": "bare"}


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "output" / "baseline"


def recorded_notes(config: dict) -> bool:
    """Runs recorded before the notes option name it through their condition."""
    if "notes" in config:
        return bool(config["notes"])
    return str(config.get("condition", "")).startswith("baseline-plus")


def _run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _print_event(message: str) -> None:
    safe = str(message).encode("ascii", errors="replace").decode("ascii")
    print(f"[agent] {safe}")


def main() -> None:
    parser = ArgumentParser(
        description="Persistent direct-play PuzzleScript agent over any harness (run inside the agents container)"
    )
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--max-decisions", type=int, default=None)
    parser.add_argument("--max-wall-seconds", type=int, default=0, help="0 = unlimited")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--harness-dir", type=Path, help="Seed a fresh workspace with these harness files (notes stay off).")
    parser.add_argument("--continue-from", default="", help="Restore an unsolved completed run in a new session; max-steps is the additional budget.")
    parser.add_argument("--notes", action="store_true",
                        help="Give the agent a notes file it reads and edits across turns.")
    parser.add_argument("--harness", choices=HARNESS_IDS, default="codex")
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
        from frameworks.baseline.continuation import load_parent
        load_parent(args.continue_from)
        parent_config = json.loads((Path(args.continue_from) / "run_config.json").read_text(encoding="utf-8"))
        if any(parent_config[key] != value for key, value in {
            "model": args.model, "reasoning_effort": args.effort, "game_id": args.game_id,
        }.items()) or recorded_notes(parent_config) != args.notes or LEGACY_HARNESS.get(parent_config.get("harness", "codex"), parent_config.get("harness", "codex")) != args.harness or parent_config.get("provider", "") != args.provider:
            raise ValueError("Continuation must preserve the parent model, effort, notes, harness, and game")
        if output_dir.resolve() == Path(args.continue_from).resolve() or output_dir.exists():
            raise ValueError("Continuation requires a fresh separate output directory")
    dashboard = None
    event_sink = _print_event
    if not args.no_window:
        from client.screen_dashboard import ScreenDashboard

        dashboard = ScreenDashboard(
            game_id=args.game_id,
            mode=args.harness.upper(),
            controls="One persistent agent session. Close or press Ctrl+C to stop.",
        )
        event_sink = dashboard.push_event

    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
        renderer=dashboard.render if dashboard is not None else None,
    )
    config = GameSessionConfig(
        model=args.model,
        effort=args.effort,
        workspace_enabled=args.notes,
        harness=args.harness,
        provider=args.provider,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "notes": args.notes,
                # Older readers group runs by condition.
                "condition": "baseline-plus" if args.notes else "baseline",
                "harness": args.harness,
                "provider": args.provider,
                "model": args.model,
                "reasoning_effort": args.effort,
                "game_id": args.game_id,
                "backend_url": args.backend_url,
                "max_steps": args.max_steps,
                "max_decisions": args.max_decisions,
                "max_wall_seconds": args.max_wall_seconds,
                "continuation_from": str(Path(args.continue_from).resolve()) if args.continue_from else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result_holder = {}

    def run_agent() -> None:
        try:
            # The agent works outside the results tree; baseline-plus notes are
            # mirrored to output_dir/workspace after every turn.
            session_workspace = Path(tempfile.mkdtemp(prefix="play-"))
            if args.continue_from:
                from frameworks.baseline.continuation import seed_notes
                seed_notes(args.continue_from, session_workspace)
            with CliGameSession(
                config,
                session_workspace,
                artifact_directory=output_dir,
                mirror_directory=output_dir / "workspace",
                workspace_seed=args.harness_dir,
            ) as session:
                if args.max_wall_seconds > 0:
                    session.deadline = time.monotonic() + args.max_wall_seconds
                runner = CodexAgentRunner(
                    env=env,
                    session=session,
                    output_dir=output_dir,
                    max_steps=args.max_steps,
                    max_decisions=args.max_decisions,
                    event_sink=event_sink,
                    workspace_enabled=config.workspace_enabled,
                    continuation_from=args.continue_from or None,
                    max_wall_seconds=args.max_wall_seconds,
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
        print("Agent run interrupted before completion.")
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
    print(f"agent_events={output_dir / 'agent_events.jsonl'}")


if __name__ == "__main__":
    main()
