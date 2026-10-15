from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
CONDITIONS = ["baseline", "baseline-plus"]


@dataclass(frozen=True)
class RunSpec:
    index: int
    model: str
    effort: str
    condition: str
    repeat: int
    output_dir: Path


def build_specs(
    *,
    models: list[str],
    efforts: list[str],
    conditions: list[str],
    repeats: int,
    output_root: Path,
) -> list[RunSpec]:
    specs: list[RunSpec] = []
    combinations = itertools.product(models, efforts, conditions, range(1, repeats + 1))
    for index, (model, effort, condition, repeat) in enumerate(combinations, start=1):
        specs.append(
            RunSpec(
                index=index,
                model=model,
                effort=effort,
                condition=condition,
                repeat=repeat,
                output_dir=output_root / f"run-{index:04d}",
            )
        )
    return specs


def read_run_outcome(spec: RunSpec, returncode: int) -> dict[str, Any]:
    outcome: dict[str, Any] = {
        **asdict(spec),
        "output_dir": str(spec.output_dir),
        "returncode": returncode,
        "status": "process_error" if returncode else "missing_result",
        "solved": False,
    }
    result_path = spec.output_dir / "result.json"
    error_path = spec.output_dir / "error.json"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        outcome.update(result)
        outcome["status"] = result.get("status", "completed")
    elif error_path.exists():
        outcome["error"] = json.loads(error_path.read_text(encoding="utf-8"))
    return outcome


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


async def _run_one(
    spec: RunSpec,
    *,
    semaphore: asyncio.Semaphore,
    total: int,
    game_id: str,
    backend_url: str,
    max_steps: int,
    harness: str,
) -> dict[str, Any]:
    async with semaphore:
        spec.output_dir.mkdir(parents=True, exist_ok=False)
        # Every run is one agents container (harnesses.launch).
        command = [
            sys.executable, "-m", "harnesses.launch",
            "--mode", spec.condition, "--harness", harness,
            "--model", spec.model, "--effort", spec.effort,
            "--game-id", game_id, "--backend-url", backend_url,
            "--max-steps", str(max_steps), "--output-dir", str(spec.output_dir),
        ]

        print(
            f"[{spec.index}/{total}] START model={spec.model} "
            f"effort={spec.effort} condition={spec.condition} repeat={spec.repeat}",
            flush=True,
        )
        started_at = datetime.now().isoformat(timespec="seconds")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            raise

        (spec.output_dir / "stdout.log").write_bytes(stdout)
        (spec.output_dir / "stderr.log").write_bytes(stderr)
        outcome = read_run_outcome(spec, int(process.returncode or 0))
        outcome["started_at"] = started_at
        outcome["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json(spec.output_dir / "batch_outcome.json", outcome)
        print(
            f"[{spec.index}/{total}] DONE solved={outcome.get('solved', False)} "
            f"actions={outcome.get('action_count', '-')} status={outcome['status']}",
            flush=True,
        )
        return outcome


async def run_batch(args: argparse.Namespace) -> list[dict[str, Any]]:
    output_root = Path(args.output_dir) if args.output_dir else (
        DEFAULT_OUTPUT_ROOT / f"batch-{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
    )
    output_root.mkdir(parents=True, exist_ok=False)
    models = args.model or ["gpt-5.5"]
    efforts = args.effort or ["medium"]
    conditions = args.condition or ["baseline-plus"]
    specs = build_specs(
        models=models,
        efforts=efforts,
        conditions=conditions,
        repeats=args.repeats,
        output_root=output_root,
    )
    config = {
        "game_id": args.game_id,
        "backend_url": args.backend_url,
        "models": models,
        "efforts": efforts,
        "conditions": conditions,
        "repeats": args.repeats,
        "parallel": args.parallel,
        "max_steps": args.max_steps,
        "harness": args.harness,
        "runs": [
            {**asdict(spec), "output_dir": str(spec.output_dir)} for spec in specs
        ],
    }
    _write_json(output_root / "batch_config.json", config)

    semaphore = asyncio.Semaphore(args.parallel)
    tasks = [
        asyncio.create_task(
            _run_one(
                spec,
                semaphore=semaphore,
                total=len(specs),
                game_id=args.game_id,
                backend_url=args.backend_url,
                max_steps=args.max_steps,
                harness=args.harness,
            )
        )
        for spec in specs
    ]
    try:
        outcomes = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    summary = {
        "total": len(outcomes),
        "solved": sum(bool(item.get("solved")) for item in outcomes),
        "process_errors": sum(int(item.get("returncode", 0)) != 0 for item in outcomes),
        "runs": outcomes,
    }
    _write_json(output_root / "summary.json", summary)
    print(f"Batch output: {output_root}", flush=True)
    print(
        f"Solved {summary['solved']}/{summary['total']}; "
        f"process errors={summary['process_errors']}",
        flush=True,
    )
    return outcomes


def _check_backend(backend_url: str, game_id: str) -> None:
    host_url = backend_url.replace("host.docker.internal", "localhost")
    response = requests.get(f"{host_url.rstrip('/')}/api/games", timeout=5)
    response.raise_for_status()
    games = response.json()
    if not any(item.get("game_id") == game_id for item in games):
        raise RuntimeError(f"Game {game_id!r} was not found at {backend_url}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a direct-play experiment matrix (one agents container per run) with bounded concurrency"
    )
    parser.add_argument("--backend-url", default="http://host.docker.internal:8000")
    parser.add_argument("--harness", default="codex",
                        choices=["codex", "claude-code", "opencode", "antigravity", "bare"])
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument("--model", action="append", help="Repeat to test multiple models")
    parser.add_argument(
        "--effort",
        action="append",
        choices=EFFORTS,
        help="Repeat to test multiple reasoning efforts",
    )
    parser.add_argument(
        "--condition",
        action="append",
        choices=CONDITIONS,
        help="Repeat to test both conditions",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.parallel < 1:
        parser.error("--parallel must be at least 1")
    return args


def main() -> None:
    args = parse_args()
    _check_backend(args.backend_url, args.game_id)
    try:
        outcomes = asyncio.run(run_batch(args))
    except KeyboardInterrupt:
        print("Batch interrupted; active child runs were terminated.", file=sys.stderr)
        raise SystemExit(130)
    if any(int(item.get("returncode", 0)) != 0 for item in outcomes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
