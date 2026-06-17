from __future__ import annotations

import argparse
import random
from pathlib import Path

from client.arc.arcade_env import ArcadeEnv
from studies.goal_recognition.experiment.collect import (
    collect_random_trajectory,
)
from studies.goal_recognition.experiment.games import load_curated_games
from studies.goal_recognition.experiment.prompts import (
    EVIDENCE_MODES,
    INPUT_MODES,
    PROMPT_ID,
    build_prompt_variants,
)
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
        description="Collect local PuzzleScript goal-recognition prompt matrix."
    )
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--games", default="curated")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument(
        "--evidence-modes",
        default=",".join(EVIDENCE_MODES),
        help="Comma-separated evidence modes: one_frame,three_random_actions.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write trajectories and prompts only. This script never calls Codex SDK.",
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


def selected_evidence_modes(args: argparse.Namespace) -> list[str]:
    modes = [item.strip() for item in args.evidence_modes.split(",") if item.strip()]
    unknown = [mode for mode in modes if mode not in EVIDENCE_MODES]
    if unknown:
        raise ValueError(f"Unknown evidence mode(s): {', '.join(unknown)}")
    return modes


def prepare_run(args: argparse.Namespace, games: list[str]):
    run_id = args.run_id or utc_run_id()
    paths = make_run_paths(args.out, run_id)
    paths.trajectories.mkdir(parents=True, exist_ok=True)
    paths.prompts.mkdir(parents=True, exist_ok=True)
    paths.predictions.touch(exist_ok=True)
    paths.errors.touch(exist_ok=True)
    paths.skips.touch(exist_ok=True)
    write_json(
        paths.manifest,
        {
            "run_id": run_id,
            "setup": "openrouter_goal_recognition_matrix",
            "backend_url": args.backend_url,
            "games": games,
            "game_count": len(games),
            "steps": args.steps,
            "seed": args.seed,
            "evidence_modes": selected_evidence_modes(args),
            "input_modes": list(INPUT_MODES),
            "prompt_id": PROMPT_ID,
            "prompt_layout": "shared prompt_prefix followed by small input-specific prompt_suffix",
            "first_image_source": str(args.dataset_dir),
            "dry_run": True,
        },
    )
    return run_id, paths


def collect_game_evidence(
    game_id: str,
    evidence_mode: str,
    args: argparse.Namespace,
    run_id: str,
    paths,
) -> None:
    rng = random.Random(args.seed + sum(ord(char) for char in game_id))
    env = ArcadeEnv(
        game_id=game_id,
        backend_url=args.backend_url,
        api_key=args.api_key,
    )
    steps = 0 if evidence_mode == "one_frame" else args.steps
    result = collect_random_trajectory(
        env,
        rng,
        steps=steps,
        evidence_mode=evidence_mode,
    )
    trajectory_name = frame_path_name(game_id)
    trajectory_path = paths.trajectories / game_id / evidence_mode / trajectory_name
    write_json(
        trajectory_path,
        {
            "run_id": run_id,
            "game_id": game_id,
            "setup": "openrouter_goal_recognition_matrix",
            "evidence_mode": evidence_mode,
            "trajectory": result.trajectory,
            "actions_taken": result.actions_taken,
            "available_actions": result.available_actions,
            "state": result.state,
            "levels_completed": result.levels_completed,
            "win_levels": result.win_levels,
            "guid": result.guid,
            "projection": result.projection,
        },
    )

    prompts = build_prompt_variants(
        game_id=game_id,
        trajectory=result.trajectory,
        available_actions=result.available_actions,
        evidence_mode=evidence_mode,
        first_image_path=(args.dataset_dir / game_id / "screenshot.png").relative_to(ROOT),
    )
    game_prompt_dir = paths.prompts / game_id / evidence_mode
    for prompt in prompts.values():
        input_mode = prompt["input_mode"]
        prompt_id = prompt["prompt_id"]
        write_json(
            game_prompt_dir / input_mode / f"{prompt_id}.json",
            {
                "run_id": run_id,
                "game_id": game_id,
                "trajectory_path": str(trajectory_path.relative_to(paths.run_dir)),
                **prompt,
            },
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    games = selected_games(args)
    run_id, paths = prepare_run(args, games)
    evidence_modes = selected_evidence_modes(args)

    for game_id in games:
        for evidence_mode in evidence_modes:
            try:
                print(f"collecting {game_id} {evidence_mode}", flush=True)
                collect_game_evidence(game_id, evidence_mode, args, run_id, paths)
            except Exception as exc:
                write_jsonl(
                    paths.errors,
                    error_row(
                        run_id=run_id,
                        game_id=game_id,
                        evidence_mode=evidence_mode,
                        error=exc,
                    ),
                )
                print(f"error {game_id} {evidence_mode}: {exc}", flush=True)

    print(f"artifacts: {paths.run_dir}")
    print(f"prompts: {paths.prompts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
