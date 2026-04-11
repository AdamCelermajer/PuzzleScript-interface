from argparse import ArgumentParser
from engine.llm_client import Config, LlmClient
from engine.agent import Agent, run_learning_loop, run_solving_loop
from engine.arcade_env import ArcadeEnv

from terminal_dashboard import TerminalDashboard


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
    dashboard = TerminalDashboard(
        game_id=args.game_id,
        mode=args.mode.upper(),
        controls="Live agent view. Press Ctrl+C to stop.",
    )
    event_sink = dashboard.push_event
    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
        renderer=dashboard.render,
    )
    llm_client = LlmClient(cfg, event_sink=event_sink)
    agent = Agent(cfg, llm_client, event_sink=event_sink)

    try:
        if args.mode == "learn":
            run_learning_loop(
                cfg,
                env,
                agent,
                dashboard=dashboard,
                event_sink=event_sink,
            )
        else:
            run_solving_loop(
                cfg,
                env,
                agent,
                dashboard=dashboard,
                event_sink=event_sink,
            )
    finally:
        dashboard.close()


if __name__ == "__main__":
    main()
