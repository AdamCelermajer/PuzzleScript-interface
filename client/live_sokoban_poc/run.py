from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.engine.arcade_env import ArcadeEnv
from client.live_sokoban_poc.live import DEFAULT_RULE_FILE, LiveSokobanController


def main() -> int:
    parser = argparse.ArgumentParser(
        description="No-LLM LIVE-style POC for ps_sokoban_basic-v1 level 1"
    )
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="local-dev")
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--output", default=str(DEFAULT_RULE_FILE))
    args = parser.parse_args()

    env = ArcadeEnv(
        game_id="ps_sokoban_basic-v1",
        backend_url=args.backend_url,
        api_key=args.api_key,
    )
    result = LiveSokobanController(env, output_path=args.output).run(
        max_steps=args.max_steps
    )
    return 0 if result.solved else 1


if __name__ == "__main__":
    raise SystemExit(main())
