from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arc_agi import Arcade, OperationMode

from client.engine.arcade_env import ArcadeEnv
from client.engine.llm_client import Config, LlmClient
from client.engine.utils import last_grid
from side_quests.one_frame_goal_recognition.prompt import build_prompt


SETUP = "one_frame"
DEFAULT_BACKEND_URL = "https://three.arcprize.org"
DEFAULT_OUT = Path("artifacts")


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-one-frame")


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


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_prediction(data: dict[str, Any]) -> dict[str, Any]:
    key_objects = data.get("key_objects")
    uncertainties = data.get("uncertainties")
    return {
        "goal_guess": _clean_string(data.get("goal_guess")),
        "win_condition_guess": _clean_string(data.get("win_condition_guess")),
        "key_objects": key_objects if isinstance(key_objects, list) else [],
        "confidence": _clean_float(data.get("confidence")),
        "uncertainties": uncertainties if isinstance(uncertainties, list) else [],
    }


def _environment_id(environment: Any) -> str:
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
    return [_environment_id(environment) for environment in arcade.get_environments()]


def selected_games(args: argparse.Namespace) -> list[str]:
    if args.game_id:
        games = [args.game_id]
    elif args.games != "all":
        games = [item.strip() for item in args.games.split(",") if item.strip()]
    else:
        games = discover_games(args.backend_url, args.api_key)

    return games[: args.limit] if args.limit else games


def make_llm(args: argparse.Namespace) -> LlmClient:
    config = Config(
        server_url=args.backend_url,
        game="goal_recognition",
        mode="one_frame",
    )
    return LlmClient(config)


def frame_path_name(game_id: str) -> str:
    return game_id.replace("/", "_").replace("\\", "_") + ".json"


def run_game(
    game_id: str,
    args: argparse.Namespace,
    llm: LlmClient,
    frames_dir: Path,
) -> dict[str, Any]:
    env = ArcadeEnv(
        game_id=game_id,
        backend_url=args.backend_url,
        api_key=args.api_key,
    )
    frame_data = env.reset()
    grid = last_grid(frame_data.frame)
    available_actions = [action.name for action in frame_data.available_actions]
    system, prompt = build_prompt(game_id, grid, available_actions)
    raw_response = llm.call_json(system, prompt, model_type=args.model_type)
    prediction = normalize_prediction(raw_response)

    write_json(
        frames_dir / frame_path_name(game_id),
        {
            "game_id": game_id,
            "setup": SETUP,
            "frames": [grid],
            "available_actions": available_actions,
            "state": frame_data.state.name,
            "levels_completed": frame_data.levels_completed,
            "win_levels": frame_data.win_levels,
            "guid": frame_data.guid,
        },
    )

    return {
        "game_id": game_id,
        "setup": SETUP,
        "frames_seen": 1,
        "actions_taken": [],
        "available_actions": available_actions,
        "state": frame_data.state.name,
        "levels_completed": frame_data.levels_completed,
        "win_levels": frame_data.win_levels,
        "prediction": prediction,
        "manual_verification": None,
        "raw_response": raw_response,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one-frame ARC goal recognition.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default=os.getenv("ARC_API_KEY", ""))
    parser.add_argument("--games", default="all")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=30)
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
            "games": games,
        },
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id, run_dir = resolve_run_dir(args)
    frames_dir = run_dir / "frames"
    predictions_path = run_dir / "predictions.jsonl"
    errors_path = run_dir / "errors.jsonl"

    run_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    predictions_path.touch(exist_ok=True)
    errors_path.touch(exist_ok=True)

    games = selected_games(args)
    done = completed_game_ids(predictions_path) if args.resume else set()
    write_manifest(run_dir / "manifest.json", run_id, args, games)
    llm = make_llm(args)

    for game_id in games:
        if game_id in done:
            print(f"skipping {game_id}")
            continue
        try:
            row = run_game(game_id, args, llm, frames_dir)
            write_jsonl(predictions_path, row)
            print(f"saved {game_id}")
        except Exception as exc:
            write_jsonl(errors_path, {"game_id": game_id, "error": str(exc)})
            print(f"error {game_id}: {exc}", file=sys.stderr)

    print(f"artifacts: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
