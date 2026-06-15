import sys
from argparse import ArgumentParser
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from client.engine.architecture import EngineArchitecture
from client.engine.llm_client import Config, LlmClient
from client.arc.arcade_env import ArcadeEnv
from client.runtime.runner import RuleReasoningLoop
from client.screen_dashboard import ScreenDashboard


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
    dashboard = ScreenDashboard(
        game_id=args.game_id,
        mode="RUN",
        controls="Engine dashboard. Close the window or press Ctrl+C to stop.",
    )
    event_sink = dashboard.push_event
    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
        renderer=dashboard.render,
    )
    llm_client = LlmClient(cfg, event_sink=event_sink)
    engine = EngineArchitecture.from_config(
        cfg, llm_client, event_sink=event_sink
    )
    loop = RuleReasoningLoop(
        env,
        engine.perceiver,
        engine.memory,
        engine.rulebook,
        engine.planner,
        engine.inducer,
        dashboard=dashboard,
        event_sink=event_sink,
    )

    def run_engine() -> None:
        loop.run(max_steps=cfg.max_steps, game_id=cfg.game)

    try:
        dashboard.run_engine(run_engine)
    finally:
        dashboard.close()


if __name__ == "__main__":
    main()
