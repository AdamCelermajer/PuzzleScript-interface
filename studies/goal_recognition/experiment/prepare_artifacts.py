from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path
from typing import Any

from client.arc.arcade_env import ArcadeEnv
from studies.goal_recognition.experiment.collect import collect_random_trajectory
from studies.goal_recognition.experiment.games import load_curated_games
from studies.goal_recognition.experiment.progress import Progress
from studies.goal_recognition.experiment.prompts import EVIDENCE_MODES
from studies.goal_recognition.experiment.schema import (
    error_row,
    frame_path_name,
    make_run_paths,
    utc_run_id,
    write_json,
    write_jsonl,
)


DEFAULT_BACKEND_URL = "http://localhost:8000"
DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_DIR = ROOT / "deploy" / "railway-human-goal-study" / "dataset"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 1: arrange source artifacts and evidence for the goal-recognition matrix."
    )
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--games", default="curated")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        "--no-arc",
        action="store_true",
        help="Arrange static artifacts only; three_random_actions evidence is marked unavailable.",
    )
    return parser.parse_args(argv)


def selected_games(args: argparse.Namespace) -> list[str]:
    if args.game_id:
        games = [args.game_id]
    elif args.games == "curated":
        games = load_curated_games()
    else:
        games = [item.strip() for item in args.games.split(",") if item.strip()]
    return games[: args.limit] if args.limit else games


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def copy_if_present(src: Path, dest: Path) -> str | None:
    if not src.exists():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return relative(dest)


def read_text_if_present(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def prepare_run(args: argparse.Namespace, games: list[str]):
    run_id = args.run_id or utc_run_id()
    paths = make_run_paths(args.out, run_id)
    for folder in (paths.sources, paths.evidence, paths.trajectories, paths.prompts, paths.batches):
        folder.mkdir(parents=True, exist_ok=True)
    paths.predictions.touch(exist_ok=True)
    paths.errors.touch(exist_ok=True)
    paths.skips.touch(exist_ok=True)
    write_json(
        paths.manifest,
        {
            "run_id": run_id,
            "setup": "openrouter_goal_recognition_matrix",
            "stage": "artifacts_prepared",
            "backend_url": args.backend_url,
            "games": games,
            "game_count": len(games),
            "seed": args.seed,
            "steps": args.steps,
            "evidence_modes": list(EVIDENCE_MODES),
            "dataset_source": str(args.dataset_dir),
            "arc_collection": not args.no_arc,
        },
    )
    return run_id, paths


def arrange_static_game(game_id: str, args: argparse.Namespace, run_id: str, paths) -> dict[str, Any]:
    source_dir = paths.sources / game_id
    dataset_game_dir = args.dataset_dir / game_id
    ascii_path = copy_if_present(dataset_game_dir / "ascii.txt", source_dir / "ascii.txt")
    screenshot_path = copy_if_present(dataset_game_dir / "screenshot.png", source_dir / "screenshot.png")
    ascii_text = read_text_if_present(source_dir / "ascii.txt")
    source = {
        "run_id": run_id,
        "game_id": game_id,
        "ascii_path": ascii_path,
        "screenshot_path": screenshot_path,
        "has_ascii": bool(ascii_text),
        "has_screenshot": screenshot_path is not None,
    }
    write_json(source_dir / "source.json", source)

    evidence = {
        "run_id": run_id,
        "game_id": game_id,
        "evidence_mode": "one_frame",
        "status": "ready" if ascii_text else "missing_ascii",
        "source": "dataset_ascii",
        "observations": [
            {
                "action": "RESET",
                "text_grid": ascii_text,
            }
        ],
        "available_actions": [],
        "image_path": screenshot_path,
    }
    write_json(paths.evidence / game_id / "one_frame.json", evidence)
    return source


def arrange_arc_evidence(game_id: str, args: argparse.Namespace, run_id: str, paths) -> None:
    if args.no_arc:
        write_json(
            paths.evidence / game_id / "three_random_actions.json",
            {
                "run_id": run_id,
                "game_id": game_id,
                "evidence_mode": "three_random_actions",
                "status": "arc_not_requested",
                "observations": [],
            },
        )
        return

    rng = random.Random(args.seed + sum(ord(char) for char in game_id))
    env = ArcadeEnv(
        game_id=game_id,
        backend_url=args.backend_url,
        api_key=args.api_key,
    )
    result = collect_random_trajectory(
        env,
        rng,
        steps=args.steps,
        evidence_mode="three_random_actions",
    )
    payload = {
        "run_id": run_id,
        "game_id": game_id,
        "evidence_mode": "three_random_actions",
        "status": "ready",
        "source": "local_arc",
        "observations": result.trajectory,
        "actions_taken": result.actions_taken,
        "available_actions": result.available_actions,
        "state": result.state,
        "levels_completed": result.levels_completed,
        "win_levels": result.win_levels,
        "guid": result.guid,
        "projection": result.projection,
    }
    evidence_path = paths.evidence / game_id / "three_random_actions.json"
    write_json(evidence_path, payload)
    write_json(paths.trajectories / game_id / "three_random_actions" / frame_path_name(game_id), payload)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    games = selected_games(args)
    run_id, paths = prepare_run(args, games)
    progress = Progress(len(games), "stage 1")

    for game_id in games:
        try:
            arrange_static_game(game_id, args, run_id, paths)
            arrange_arc_evidence(game_id, args, run_id, paths)
        except Exception as exc:
            write_jsonl(
                paths.errors,
                error_row(run_id=run_id, game_id=game_id, error=exc),
            )
        progress.step(game_id)

    print(f"artifacts: {paths.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
