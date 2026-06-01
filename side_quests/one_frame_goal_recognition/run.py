from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from arc_agi import Arcade, OperationMode

from client.engine.arcade_env import ArcadeEnv
from client.engine.llm_client import Config
from client.engine.utils import extract_json, last_grid
from side_quests.keys import default_arc_api_key, goal_recognition_config
from side_quests.one_frame_goal_recognition.prompt import build_prompt


SETUP = "one_frame"
DEFAULT_BACKEND_URL = "https://three.arcprize.org"
DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
SOCKET_TIMEOUT_SECONDS = 15.0


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


class OpenRouterJsonClient:
    """Small direct client for one-off goal-recognition JSON calls."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def call_json(
        self,
        system: str,
        prompt: str,
        *,
        model_type: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        body = {
            "model": self._model_name(model_type),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        payload = json.dumps(body).encode("utf-8")
        api_request = request.Request(
            OPENROUTER_CHAT_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.config.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            raw_body = self._read_response_with_deadline(api_request, timeout_seconds)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"OpenRouter request failed: {exc.reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(
                f"OpenRouter request timed out after {timeout_seconds:g}s"
            ) from exc

        data = json.loads(raw_body)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(
                f"OpenRouter response missing message content: {data}"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OpenRouter returned empty content")

        parsed = json.loads(extract_json(content))
        if not isinstance(parsed, dict):
            raise ValueError("LLM JSON response must be an object")
        return parsed

    def _model_name(self, model_type: str) -> str:
        return self.config.pro_model if model_type == "pro" else self.config.flash_model

    def _read_response_with_deadline(
        self,
        api_request: request.Request,
        timeout_seconds: float,
    ) -> str:
        if timeout_seconds <= 0:
            with request.urlopen(api_request, timeout=None) as response:
                return response.read().decode("utf-8")

        deadline = time.monotonic() + timeout_seconds
        socket_timeout = min(timeout_seconds, SOCKET_TIMEOUT_SECONDS)
        chunks: list[bytes] = []
        with request.urlopen(api_request, timeout=socket_timeout) as response:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                chunk = response.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")


def make_llm(args: argparse.Namespace) -> OpenRouterJsonClient:
    return OpenRouterJsonClient(
        goal_recognition_config(backend_url=args.backend_url, mode="one_frame")
    )


def frame_path_name(game_id: str) -> str:
    return game_id.replace("/", "_").replace("\\", "_") + ".json"


def run_game(
    game_id: str,
    args: argparse.Namespace,
    llm: OpenRouterJsonClient,
    frames_dir: Path,
    prompts_dir: Path,
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
            "frames": [grid],
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
        "frames_seen": 1,
        "actions_taken": [],
        "available_actions": available_actions,
        "review_evidence": {
            "frames": [grid],
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
    parser = argparse.ArgumentParser(description="Run one-frame ARC goal recognition.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default=default_arc_api_key())
    parser.add_argument("--games", default="all")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model-type", choices=["flash", "pro"], default="flash")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of games to run concurrently. OpenRouter still receives one request per game.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=90.0,
        help="OpenRouter HTTP timeout in seconds for each game prediction.",
    )
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


def run_batch(
    games: list[str],
    args: argparse.Namespace,
    llm: OpenRouterJsonClient,
    frames_dir: Path,
    prompts_dir: Path,
    predictions_path: Path,
    errors_path: Path,
) -> None:
    if len(games) == 1:
        game_id = games[0]
        result_type, row = run_game_job(game_id, args, llm, frames_dir, prompts_dir)
        write_result(result_type, row, predictions_path, errors_path)
        return

    with ThreadPoolExecutor(max_workers=len(games)) as executor:
        futures = {
            executor.submit(
                run_game_job,
                game_id,
                args,
                llm,
                frames_dir,
                prompts_dir,
            ): game_id
            for game_id in games
        }
        for future in as_completed(futures):
            result_type, row = future.result()
            write_result(result_type, row, predictions_path, errors_path)


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

    batch_size = max(1, args.batch_size)
    pending_games = []
    for game_id in games:
        if game_id in done:
            print(f"skipping {game_id}", flush=True)
            continue
        pending_games.append(game_id)

    for start in range(0, len(pending_games), batch_size):
        run_batch(
            pending_games[start : start + batch_size],
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
