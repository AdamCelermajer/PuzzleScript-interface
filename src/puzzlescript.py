

from argparse import ArgumentParser
from engine.llm_client import Config, LlmClient
from engine.agent import Agent, run_learning_loop, run_solving_loop
from envs.puzzlescript_env import PuzzleScriptEnv

def main():
    parser = ArgumentParser(description="AI Agent for PuzzleScript Worlds")
    parser.add_argument("--game", type=str, default="sokoban-basic")
    parser.add_argument("--max_steps", type=int, default=50)
    parser.add_argument("--mode", type=str, choices=["learn", "solve"], default="learn")
    args = parser.parse_args()

    cfg = Config(game=args.game, max_steps=args.max_steps, mode=args.mode)
    
    # 1. Instantiate specific environment
    env = PuzzleScriptEnv(cfg.game, cfg.server_url)
    
    # 2. Use generic engine behind the curtain
    llm_client = LlmClient(cfg)
    agent = Agent(cfg, llm_client)

    if args.mode == "learn":
        run_learning_loop(cfg, env, agent)
    else:
        run_solving_loop(cfg, env, agent)

if __name__ == "__main__":
    main()
