from argparse import ArgumentParser
from engine.llm_client import Config, LlmClient
from engine.agent import Agent, run_learning_loop, run_solving_loop
from engine.arcade_env import ArcadeEnv


def main():
    parser = ArgumentParser(description="AI Agent for ARC-compatible environments")
    parser.add_argument("--game-id", type=str, default="sokoban-basic-v1")
    parser.add_argument("--backend-url", type=str, default="http://localhost:8000")
    parser.add_argument("--max_steps", type=int, default=50)
    parser.add_argument("--mode", type=str, choices=["learn", "solve"], default="learn")
    args = parser.parse_args()

    cfg = Config(
        game=args.game_id,
        max_steps=args.max_steps,
        mode=args.mode,
        server_url=args.backend_url,
    )
    env = ArcadeEnv(game_id=args.game_id, backend_url=args.backend_url)
    llm_client = LlmClient(cfg)
    agent = Agent(cfg, llm_client)

    if args.mode == "learn":
        run_learning_loop(cfg, env, agent)
    else:
        run_solving_loop(cfg, env, agent)


if __name__ == "__main__":
    main()
