import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from argparse import ArgumentParser
from engine.llm_client import Config, LlmClient
from engine.agent import Agent, run_learning_loop, run_solving_loop
from envs.arc_env import ArcAgiEnv

def main():
    parser = ArgumentParser(description="AI Agent for ARC-AGI-3 Benchmarks")
    parser.add_argument("--task", type=str, default="task_001")
    parser.add_argument("--max_steps", type=int, default=50)
    parser.add_argument("--mode", type=str, choices=["learn", "solve"], default="learn")
    args = parser.parse_args()

    # Map 'task' to generic 'game' inside Config
    cfg = Config(game=args.task, max_steps=args.max_steps, mode=args.mode)
    
    # 1. Instantiate specific ARC environment
    env = ArcAgiEnv(args.task)
    
    # 2. Use generic engine behind the curtain
    llm_client = LlmClient(cfg)
    agent = Agent(cfg, llm_client)

    if args.mode == "learn":
        run_learning_loop(cfg, env, agent)
    else:
        run_solving_loop(cfg, env, agent)

if __name__ == "__main__":
    main()
