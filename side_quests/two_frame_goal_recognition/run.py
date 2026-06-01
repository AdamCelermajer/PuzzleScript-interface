from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arc_agi import Arcade, OperationMode

from client.engine.arcade_env import ArcadeEnv
from client.engine.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid
from side_quests.keys import default_arc_api_key, goal_recognition_config
from side_quests.one_frame_goal_recognition.run import (
    OpenRouterJsonClient,
    completed_game_ids,
    frame_path_name,
    write_json,
    write_jsonl,
)
from side_quests.two_frame_goal_recognition.prompt import build_prompt


SETUP = "two_frame"
DEFAULT_BACKEND_URL = "https://three.arcprize.org"
DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts"


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-two-frame")


def clean_goal(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_prediction(data: dict[str, Any]) -> dict[str, Any]:
    return {"goal_guess": clean_goal(data.get("goal_guess"))}


def environment_id(environment: Any) -> str:
    for attr in ("id", "game_id", "name"):
        value = getattr(environment, attr, None)
        if value:
            return str(value)
    return str(environment)


def discover_games(backend_url: str, api_key: str) -> list[str]:
    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=backend_url,
        arc_api_key=api_key,
    )
    return [environment_id(environment) for environment in arcade.get_environments()]


def selected_games(args: argparse.Namespace) -> list[str]:
    if args.game_id:
        games = [args.game_id]
    elif args.games != "all":
        games = [item.strip() for item in args.games.split(",") if item.strip()]
    else:
        games = discover_games(args.backend_url, args.api_key)

    return games[: args.limit] if args.limit else games


def make_llm(args: argparse.Namespace) -> OpenRouterJsonClient:
    return OpenRouterJsonClient(
        goal_recognition_config(backend_url=args.backend_url, mode="two_frame")
    )


def choose_action(frame_data: FrameData, rng: random.Random) -> GameAction | None:
    controls = {GameAction.RESET, GameAction.ACTION7}
    actions = [
        action
        for action in frame_data.available_actions
        if action not in controls
    ]
    if not actions:
        actions = list(frame_data.available_actions)
    if not actions:
        return None
    return rng.choice(actions)


def action_data(
    action: GameAction,
    frame_data: FrameData,
    rng: random.Random,
) -> dict[str, int] | None:
    if action != GameAction.ACTION6:
        return None

    grid = last_grid(frame_data.frame)
    height = len(grid)
    width = len(grid[0]) if height else 0
    if width <= 0 or height <= 0:
        return None
    return {"x": rng.randrange(width), "y": rng.randrange(height)}


def action_label(action: GameAction, data: dict[str, int] | None) -> str:
    if not data:
        return action.name
    return f"{action.name} {json.dumps(data, sort_keys=True)}"


def collect_two_frame_trajectory(
    env: ArcadeEnv,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[str], FrameData]:
    frame_data = env.reset()
    trajectory = [{"action": GameAction.RESET.name, "grid": last_grid(frame_data.frame)}]
    actions_taken: list[str] = []

    if frame_data.state not in {GameState.WIN, GameState.GAME_OVER}:
        action = choose_action(frame_data, rng)
        if action is not None:
            data = action_data(action, frame_data, rng)
            label = action_label(action, data)
            actions_taken.append(label)
            frame_data = env.step(action, data=data)
            trajectory.append({"action": label, "grid": last_grid(frame_data.frame)})

    return trajectory, actions_taken, frame_data


def run_game(
    game_id: str,
    args: argparse.Namespace,
    llm: OpenRouterJsonClient,
    frames_dir: Path,
    prompts_dir: Path,
) -> dict[str, Any]:
    rng = random.Random(args.seed + sum(ord(char) for char in game_id))
    env = ArcadeEnv(
        game_id=game_id,
        backend_url=args.backend_url,
        api_key=args.api_key,
    )
    trajectory, actions_taken, frame_data = collect_two_frame_trajectory(env, rng)
    if len(trajectory) != 2:
        raise RuntimeError("Could not collect exactly two frames for this game")
    available_actions = [action.name for action in frame_data.available_actions]
    system, prompt = build_prompt(game_id, trajectory, available_actions)
    write_json(
        prompts_dir / frame_path_name(game_id),
        {
            "game_id": game_id,
            "setup": SETUP,
            "system": system,
            "prompt": prompt,
        },
    )
    write_json(
        frames_dir / frame_path_name(game_id),
        {
            "game_id": game_id,
            "setup": SETUP,
            "trajectory": trajectory,
            "actions_taken": actions_taken,
            "available_actions": available_actions,
            "state": frame_data.state.name,
            "levels_completed": frame_data.levels_completed,
            "win_levels": frame_data.win_levels,
            "guid": frame_data.guid,
        },
    )
    raw_response = llm.call_json(
        system,
        prompt,
        model_type=args.model_type,
        timeout_seconds=args.request_timeout,
    )
    prediction = normalize_prediction(raw_response)

    return {
        "game_id": game_id,
        "setup": SETUP,
        "frames_seen": len(trajectory),
        "actions_taken": actions_taken,
        "available_actions": available_actions,
        "review_evidence": {
            "trajectory": trajectory,
            "available_actions": available_actions,
        },
        "state": frame_data.state.name,
        "levels_completed": frame_data.levels_completed,
        "win_levels": frame_data.win_levels,
        "prediction": prediction,
        "manual_verification": None,
        "raw_response": raw_response,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run two-frame ARC goal recognition.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default=default_arc_api_key())
    parser.add_argument("--games", default="all")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model-type", choices=["flash", "pro"], default="flash")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--request-timeout", type=float, default=90.0)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def latest_run_dir(out_dir: Path) -> Path | None:
    if (out_dir / "manifest.json").exists():
        return out_dir
    if not out_dir.exists():
        return None

    run_dirs = [
        path
        for path in out_dir.iterdir()
        if path.is_dir() and (path / "manifest.json").exists()
    ]
    if not run_dirs:
        return None
    return max(run_dirs, key=lambda path: path.stat().st_mtime)


def resolve_run_dir(args: argparse.Namespace) -> tuple[str, Path]:
    if args.resume:
        existing = latest_run_dir(args.out)
        if existing is not None:
            return existing.name, existing

    run_id = utc_run_id()
    return run_id, args.out / run_id


def write_manifest(
    path: Path,
    run_id: str,
    args: argparse.Namespace,
    games: list[str],
) -> None:
    write_json(
        path,
        {
            "run_id": run_id,
            "setup": SETUP,
            "backend_url": args.backend_url,
            "model_type": args.model_type,
            "limit": args.limit,
            "seed": args.seed,
            "batch_size": args.batch_size,
            "request_timeout": args.request_timeout,
            "games": games,
        },
    )


def run_game_job(
    game_id: str,
    args: argparse.Namespace,
    llm: OpenRouterJsonClient,
    frames_dir: Path,
    prompts_dir: Path,
) -> tuple[str, dict[str, Any]]:
    print(f"running {game_id}", flush=True)
    try:
        return "prediction", run_game(game_id, args, llm, frames_dir, prompts_dir)
    except Exception as exc:
        return "error", {"game_id": game_id, "error": str(exc)}


def write_result(
    result_type: str,
    row: dict[str, Any],
    predictions_path: Path,
    errors_path: Path,
) -> None:
    game_id = str(row.get("game_id", ""))
    if result_type == "prediction":
        write_jsonl(predictions_path, row)
        print(f"saved {game_id}", flush=True)
        return

    write_jsonl(errors_path, row)
    print(f"error {game_id}: {row.get('error')}", file=sys.stderr, flush=True)


def run_pending_games(
    games: list[str],
    args: argparse.Namespace,
    llm: OpenRouterJsonClient,
    frames_dir: Path,
    prompts_dir: Path,
    predictions_path: Path,
    errors_path: Path,
) -> None:
    max_workers = max(1, args.batch_size)
    game_iter = iter(games)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}

        def submit_next() -> None:
            try:
                game_id = next(game_iter)
            except StopIteration:
                return
            futures[
                executor.submit(
                    run_game_job,
                    game_id,
                    args,
                    llm,
                    frames_dir,
                    prompts_dir,
                )
            ] = game_id

        for _ in range(min(max_workers, len(games))):
            submit_next()

        while futures:
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in completed:
                futures.pop(future)
                result_type, row = future.result()
                write_result(result_type, row, predictions_path, errors_path)
                submit_next()


def run_batch(
    games: list[str],
    args: argparse.Namespace,
    llm: OpenRouterJsonClient,
    frames_dir: Path,
    prompts_dir: Path,
    predictions_path: Path,
    errors_path: Path,
) -> None:
    with ThreadPoolExecutor(max_workers=len(games)) as executor:
        futures = [
            executor.submit(
                run_game_job,
                game_id,
                args,
                llm,
                frames_dir,
                prompts_dir,
            )
            for game_id in games
        ]
        for future in futures:
            result_type, row = future.result()
            write_result(result_type, row, predictions_path, errors_path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id, run_dir = resolve_run_dir(args)
    frames_dir = run_dir / "frames"
    prompts_dir = run_dir / "prompts"
    predictions_path = run_dir / "predictions.jsonl"
    errors_path = run_dir / "errors.jsonl"

    run_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    predictions_path.touch(exist_ok=True)
    errors_path.touch(exist_ok=True)

    games = selected_games(args)
    done = completed_game_ids(predictions_path) if args.resume else set()
    write_manifest(run_dir / "manifest.json", run_id, args, games)
    llm = make_llm(args)

    pending_games = []
    for game_id in games:
        if game_id in done:
            print(f"skipping {game_id}", flush=True)
            continue
        pending_games.append(game_id)

    run_pending_games(
        pending_games,
        args,
        llm,
        frames_dir,
        prompts_dir,
        predictions_path,
        errors_path,
    )

    print(f"artifacts: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
