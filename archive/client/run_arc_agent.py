import sys
from argparse import ArgumentParser
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from client.engine.architecture import EngineArchitecture
from client.engine.llm_client import Config, LlmClient
from client.arc.arcade_env import ArcadeEnv
from client.runtime.runner import RuleReasoningLoop


def main():
    parser = ArgumentParser(description="AI Agent for ARC-compatible environments")
    parser.add_argument("--game-id", type=str, default="ps_sokoban_basic-v1")
    parser.add_argument("--backend-url", type=str, default="http://localhost:8000")
    parser.add_argument("--max_steps", type=int, default=50)
    args = parser.parse_args()

    cfg = Config(
        game=args.game_id,
        max_steps=args.max_steps,
        server_url=args.backend_url,
    )
    event_sink = print
    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
    )
    llm_client = LlmClient(cfg, event_sink=event_sink)
    engine = EngineArchitecture.from_config(
        cfg, llm_client, event_sink=event_sink
    )
    loop = RuleReasoningLoop(
        env,
        engine,
        event_sink=event_sink,
    )
    result = loop.run(max_steps=cfg.max_steps, game_id=cfg.game)
    print(f"run_status={result.status}")
    print(f"run_reason={result.reason}")


if __name__ == "__main__":
    main()
