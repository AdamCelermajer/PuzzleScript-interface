from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arc_agi import Arcade, OperationMode

from client.engine.arcade_env import ArcadeEnv
from client.engine.llm_client import LlmClient
from client.engine.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid
from side_quests.keys import default_arc_api_key, goal_recognition_config
from side_quests.ten_frame_goal_recognition.prompt import build_prompt


SETUP = "ten_frame_random"
DEFAULT_BACKEND_URL = "https://three.arcprize.org"
DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts"


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-ten-frame")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data) + "\n")


def completed_game_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    completed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        game_id = str(row.get("game_id", "")).strip()
        if game_id:
            completed.add(game_id)
    return completed


def frame_path_name(game_id: str) -> str:
    return game_id.replace("/", "_").replace("\\", "_") + ".json"


def normalize_prediction(data: dict[str, Any]) -> dict[str, Any]:
    key_objects = data.get("key_objects")
    uncertainties = data.get("uncertainties")
    return {
        "goal_guess": str(data.get("goal_guess", "")).strip(),
        "win_condition_guess": str(data.get("win_condition_guess", "")).strip(),
        "key_objects": key_objects if isinstance(key_objects, list) else [],
        "confidence": float(data.get("confidence", 0.0) or 0.0),
        "uncertainties": uncertainties if isinstance(uncertainties, list) else [],
    }


def choose_random_action(
    frame_data: FrameData,
    rng: random.Random,
) -> GameAction | None:
    actions = [
        action
        for action in frame_data.available_actions
        if action not in {GameAction.RESET, GameAction.ACTION6, GameAction.ACTION7}
    ]
    if not actions:
        actions = list(frame_data.available_actions)
    if not actions:
        return None
    return rng.choice(actions)


def discover_games(backend_url: str, api_key: str) -> list[str]:
    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=backend_url,
        arc_api_key=api_key,
    )
    games = arcade.get_environments()
    return [str(getattr(game, "id", getattr(game, "game_id", game))) for game in games]


def selected_games(args: argparse.Namespace) -> list[str]:
    if args.game_id:
        return [args.game_id]
    if args.games != "all":
        return [item.strip() for item in args.games.split(",") if item.strip()]

    games = discover_games(args.backend_url, args.api_key)
    return games[: args.limit] if args.limit else games


def make_llm(args: argparse.Namespace) -> LlmClient:
    return LlmClient(
        goal_recognition_config(backend_url=args.backend_url, mode="ten_frame_random")
    )


def collect_trajectory(
    env: ArcadeEnv,
    steps: int,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[str], FrameData]:
    frame_data = env.reset()
    trajectory = [{"action": GameAction.RESET.name, "grid": last_grid(frame_data.frame)}]
    actions_taken: list[str] = []

    for _ in range(steps):
        if frame_data.state in {GameState.WIN, GameState.GAME_OVER}:
            break

        action = choose_random_action(frame_data, rng)
        if action is None:
            break

        actions_taken.append(action.name)
        frame_data = env.step(action)
        trajectory.append({"action": action.name, "grid": last_grid(frame_data.frame)})

    return trajectory, actions_taken, frame_data


def run_game(
    game_id: str,
    args: argparse.Namespace,
    llm: LlmClient,
    frames_dir: Path,
) -> dict[str, Any]:
    rng = random.Random(args.seed + sum(ord(char) for char in game_id))
    env = ArcadeEnv(game_id=game_id, backend_url=args.backend_url, api_key=args.api_key)
    trajectory, actions_taken, frame_data = collect_trajectory(env, args.steps, rng)
    available_actions = [action.name for action in frame_data.available_actions]
    system, prompt = build_prompt(game_id, trajectory, available_actions)
    raw_response = llm.call_json(system, prompt, model_type=args.model_type)
    prediction = normalize_prediction(raw_response)

    write_json(
        frames_dir / frame_path_name(game_id),
        {
            "game_id": game_id,
            "setup": SETUP,
            "trajectory": trajectory,
            "actions_taken": actions_taken,
            "available_actions": available_actions,
            "guid": frame_data.guid,
        },
    )

    return {
        "game_id": game_id,
        "setup": SETUP,
        "frames_seen": len(trajectory),
        "actions_taken": actions_taken,
        "available_actions": available_actions,
        "state": frame_data.state.name,
        "levels_completed": frame_data.levels_completed,
        "win_levels": frame_data.win_levels,
        "prediction": prediction,
        "manual_verification": None,
        "raw_response": raw_response,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ten-frame random-action goal recognition."
    )
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default=default_arc_api_key())
    parser.add_argument("--games", default="all")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model-type", choices=["flash", "pro"], default="flash")
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id, run_dir = resolve_run_dir(args)
    frames_dir = run_dir / "frames"
    predictions_path = run_dir / "predictions.jsonl"
    errors_path = run_dir / "errors.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    llm = make_llm(args)
    games = selected_games(args)
    done = completed_game_ids(predictions_path) if args.resume else set()
    write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "setup": SETUP,
            "backend_url": args.backend_url,
            "model_type": args.model_type,
            "limit": args.limit,
            "steps": args.steps,
            "seed": args.seed,
            "games": games,
        },
    )

    for game_id in games:
        if game_id in done:
            continue
        try:
            row = run_game(game_id, args, llm, frames_dir)
            write_jsonl(predictions_path, row)
            print(f"saved {game_id}")
        except Exception as exc:
            write_jsonl(errors_path, {"game_id": game_id, "error": str(exc)})
            print(f"error {game_id}: {exc}", file=sys.stderr)

    print(f"predictions: {predictions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
