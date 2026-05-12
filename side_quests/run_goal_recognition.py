from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "side_quests" / "run_logs"
ONE_ARTIFACTS = ROOT / "side_quests" / "one_frame_goal_recognition" / "artifacts"
TEN_ARTIFACTS = ROOT / "side_quests" / "ten_frame_goal_recognition" / "artifacts"


@dataclass
class RunView:
    name: str
    process: subprocess.Popen
    log_path: Path
    artifacts_root: Path


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def latest_run_dir(path: Path) -> Path | None:
    if not path.exists():
        return None
    run_dirs = [item for item in path.iterdir() if item.is_dir()]
    if not run_dirs:
        return None
    return max(run_dirs, key=lambda item: item.stat().st_mtime)


def read_manifest(run_dir: Path | None) -> dict:
    if run_dir is None:
        return {}
    path = run_dir / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_counts(artifacts_root: Path) -> tuple[int, int, int, Path | None]:
    run_dir = latest_run_dir(artifacts_root)
    manifest = read_manifest(run_dir)
    total = len(manifest.get("games") or [])
    predictions = count_jsonl(run_dir / "predictions.jsonl") if run_dir else 0
    errors = count_jsonl(run_dir / "errors.jsonl") if run_dir else 0
    return predictions, errors, total, run_dir


def tail(path: Path, lines: int = 6) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def launch(name: str, module: str, args: list[str], log_path: Path, artifacts_root: Path) -> RunView:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", module, *args]
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return RunView(name=name, process=process, log_path=log_path, artifacts_root=artifacts_root)


def render(runs: list[RunView]) -> None:
    clear_screen()
    print("ARC goal-recognition runs")
    print("Press Ctrl+C to stop the interface and child processes.")
    print("")
    for run in runs:
        predictions, errors, total, run_dir = run_counts(run.artifacts_root)
        state = "running" if run.process.poll() is None else f"exited {run.process.returncode}"
        done = predictions + errors
        total_text = str(total) if total else "?"
        print(f"{run.name}: {state} | done {done}/{total_text} | predictions {predictions} | errors {errors}")
        print(f"  log: {run.log_path}")
        if run_dir:
            print(f"  artifacts: {run_dir}")
            print(f"  prompts: {run_dir / 'prompts'}")
        for line in tail(run.log_path):
            print(f"    {line}")
        print("")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run both goal-recognition setups with visible progress.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--model-type", choices=["flash", "pro"], default="flash")
    parser.add_argument("--backend-url", default="https://three.arcprize.org")
    parser.add_argument("--refresh", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    common = [
        "--backend-url",
        args.backend_url,
        "--limit",
        str(args.limit),
        "--model-type",
        args.model_type,
    ]
    runs = [
        launch(
            "one-frame",
            "side_quests.one_frame_goal_recognition.run",
            common,
            LOG_DIR / f"one-frame-{stamp}.log",
            ONE_ARTIFACTS,
        ),
        launch(
            "ten-frame",
            "side_quests.ten_frame_goal_recognition.run",
            [*common, "--steps", str(args.steps), "--seed", str(args.seed)],
            LOG_DIR / f"ten-frame-{stamp}.log",
            TEN_ARTIFACTS,
        ),
    ]

    try:
        while True:
            render(runs)
            if all(run.process.poll() is not None for run in runs):
                return max(run.process.returncode or 0 for run in runs)
            time.sleep(args.refresh)
    except KeyboardInterrupt:
        for run in runs:
            if run.process.poll() is None:
                run.process.terminate()
        print("\nStopped child runs.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
