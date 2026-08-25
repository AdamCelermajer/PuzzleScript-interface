from __future__ import annotations

import json
import shutil
import sys
import tempfile
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.arc.arcade_env import ArcadeEnv
from avo.legacy.openrouter_session import OpenRouterAvoConfig, OpenRouterAvoSession
from avo.legacy.runner import AvoAgentRunner
from avo.legacy.session import AvoCodexSession, AvoSessionConfig
from client.screen_dashboard import ScreenDashboard


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "output"


def _run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _print_event(message: str) -> None:
    safe = str(message).encode("ascii", errors="replace").decode("ascii")
    print(f"[avo] {safe}")


def _archive_workspace(source: Path, destination: Path) -> dict[str, list[str]]:
    """Best-effort archive; Codex sandbox ACLs can outlive a Windows session."""
    report: dict[str, list[str]] = {"copied": [], "skipped": []}
    destination.mkdir(parents=True, exist_ok=True)

    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            report["copied"].append(relative.as_posix())
        except OSError as exc:
            report["skipped"].append(f"{relative.as_posix()}: {exc}")

    return report


def main() -> None:
    parser = ArgumentParser(
        description="AVO-inspired long-horizon client for ARC-compatible puzzle games"
    )
    parser.add_argument(
        "--provider",
        default="codex",
        choices=["codex", "openrouter"],
        help="Coding-agent backend. OpenRouter uses a bounded local tool loop.",
    )
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument(
        "--model",
        default="",
        help=(
            "Model ID. Defaults to gpt-5.6-sol for Codex or "
            "anthropic/claude-opus-5-fast for OpenRouter."
        ),
    )
    parser.add_argument(
        "--codex-bin",
        default="",
        help="Optional Codex CLI path; the installed Codex app is detected by default.",
    )
    parser.add_argument(
        "--effort",
        default="high",
        choices=["minimal", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument(
        "--supervisor-effort",
        default="medium",
        choices=["minimal", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--max-decisions", type=int, default=None)
    parser.add_argument("--max-batch-actions", type=int, default=20)
    parser.add_argument("--max-tool-rounds", type=int, default=12)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument(
        "--visual",
        action="store_true",
        help="Also send the rendered PNG; default is the text-grid-only AVO condition.",
    )
    parser.add_argument(
        "--supervise-after-stalls",
        type=int,
        default=3,
        help="Ask the independent supervisor after this many consecutive no-change actions; 0 disables it.",
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument(
        "--resume-from",
        default="",
        help=(
            "Optional prior AVO output or workspace. Restores only durable notes "
            "and helper code into a fresh environment session."
        ),
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Run headless without the tkinter dashboard.",
    )
    args = parser.parse_args()
    model = args.model or (
        "anthropic/claude-opus-5-fast"
        if args.provider == "openrouter"
        else "gpt-5.6-sol"
    )

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else DEFAULT_OUTPUT_ROOT / _run_id()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "client": "AVO-inspired",
                "provider": args.provider,
                "game_id": args.game_id,
                "backend_url": args.backend_url,
                "model": model,
                "effort": args.effort,
                "supervisor_effort": args.supervisor_effort,
                "max_steps": args.max_steps,
                "max_decisions": args.max_decisions,
                "max_batch_actions": args.max_batch_actions,
                "max_tool_rounds": args.max_tool_rounds,
                "max_output_tokens": args.max_output_tokens,
                "supervise_after_stalls": args.supervise_after_stalls,
                "visual": args.visual,
                "resume_from": args.resume_from,
                "workspace_isolation": "external temporary directory",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    dashboard = None
    event_sink = _print_event
    if not args.no_window:
        dashboard = ScreenDashboard(
            game_id=args.game_id,
            mode="AVO",
            controls=(
                "Persistent coding agent with durable memory and stagnation supervisor. "
                "Close or press Ctrl+C to stop."
            ),
        )
        event_sink = dashboard.push_event

    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
        renderer=dashboard.render if dashboard is not None else None,
    )
    if args.provider == "openrouter":
        session_context = OpenRouterAvoSession(
            OpenRouterAvoConfig(
                model=model,
                effort=args.effort,
                supervisor_effort=args.supervisor_effort,
                max_output_tokens=args.max_output_tokens,
                max_tool_rounds=args.max_tool_rounds,
            ),
            Path(tempfile.mkdtemp(prefix="avo-puzzle-run-")),
        )
    else:
        session_context = AvoCodexSession(
            AvoSessionConfig(
                model=model,
                effort=args.effort,
                supervisor_effort=args.supervisor_effort,
                codex_bin=args.codex_bin,
            ),
            Path(tempfile.mkdtemp(prefix="avo-puzzle-run-")),
        )
    result_holder = {}
    isolated_workspace = session_context.working_directory
    if args.resume_from:
        resume_root = Path(args.resume_from).resolve()
        if (resume_root / "workspace").is_dir():
            resume_root = resume_root / "workspace"
        restored = []
        for relative in (
            "KNOWLEDGE.md",
            "helpers/solver.py",
            "helpers/scratch.py",
        ):
            source = resume_root / relative
            if source.is_file():
                target = isolated_workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                restored.append(relative)
        prior_state = resume_root / "current_state.json"
        if prior_state.is_file():
            target = isolated_workspace / "prior_run_final_state.json"
            shutil.copy2(prior_state, target)
            restored.append("prior_run_final_state.json")
        if not restored:
            raise ValueError(
                f"No durable AVO files found under resume path: {resume_root}"
            )
        _print_event(f"restored durable workspace files: {', '.join(restored)}")

    def run_agent() -> None:
        with session_context as session:
            try:
                runner = AvoAgentRunner(
                    env=env,
                    session=session,
                    output_dir=output_dir,
                    workspace_dir=isolated_workspace,
                    max_steps=args.max_steps,
                    max_decisions=args.max_decisions,
                    max_batch_actions=args.max_batch_actions,
                    supervise_after_stalls=args.supervise_after_stalls,
                    use_visual=args.visual,
                    event_sink=event_sink,
                )
                result_holder["result"] = runner.run()
            finally:
                if hasattr(session, "usage_summary"):
                    result_holder["usage"] = session.usage_summary()

    try:
        if dashboard is None:
            run_agent()
        else:
            try:
                dashboard.run_engine(run_agent)
            finally:
                dashboard.close()
    finally:
        archive_report = _archive_workspace(
            isolated_workspace,
            output_dir / "workspace",
        )
        (output_dir / "workspace_archive.json").write_text(
            json.dumps(archive_report, indent=2),
            encoding="utf-8",
        )
        if archive_report["skipped"]:
            _print_event(
                f"workspace archive skipped {len(archive_report['skipped'])} "
                "sandbox-protected file(s); see workspace_archive.json"
            )
        if result_holder.get("usage"):
            (output_dir / "provider_usage.json").write_text(
                json.dumps(result_holder["usage"], indent=2),
                encoding="utf-8",
            )

    result = result_holder.get("result")
    if result is None:
        print("AVO run interrupted before completion.")
        print(f"output_dir={output_dir}")
        return

    print(f"solved={result.solved}")
    print(f"status={result.status}")
    print(f"reason={result.reason}")
    print(f"actions={[action.name for action in result.actions]}")
    print(f"decisions={result.decisions}")
    print(f"supervisor_calls={result.supervisor_calls}")
    if result_holder.get("usage"):
        print(f"provider_usage={json.dumps(result_holder['usage'])}")
    print(f"output_dir={result.output_dir}")
    print(f"transcript={result.transcript_path}")
    print(f"trajectory={output_dir / 'workspace' / 'trajectory.jsonl'}")


if __name__ == "__main__":
    main()
