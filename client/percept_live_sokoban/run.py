from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.engine.arcade_env import ArcadeEnv
from client.percept_live_sokoban.model import SymbolGoal
from client.percept_live_sokoban.rules import (
    DEFAULT_JOURNAL_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_STORE_PATH,
    PerceptRuleModel,
)
from client.percept_live_sokoban.runner import PerceptLiveRunner
from client.terminal_dashboard import TerminalDashboard


DEFAULT_GOAL_PATH = Path(__file__).resolve().parent / "goals" / "level1_goal.json"


def load_goal(path: Path) -> SymbolGoal:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SymbolGoal.from_cells(data["required_cells"])


def main() -> None:
    parser = ArgumentParser(description="Symbol-percept LIVE-style Sokoban experiment")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument("--goal", type=Path, default=DEFAULT_GOAL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL_PATH)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--fresh-memory", action="store_true")
    parser.add_argument("--no-dashboard", action="store_true")
    args = parser.parse_args()

    if args.fresh_memory:
        for path in (args.output, args.store, args.journal):
            if path.exists():
                path.unlink()

    goal = load_goal(args.goal)
    model = PerceptRuleModel(
        output_path=args.output,
        store_path=args.store,
        journal_path=args.journal,
        load_existing=not args.fresh_memory,
    )

    dashboard = None
    renderer = None
    event_sink = print
    if not args.no_dashboard:
        dashboard = TerminalDashboard(
            game_id=args.game_id,
            mode="PERCEPT-LIVE",
            controls="Symbol-percept experiment. Press Ctrl+C to stop.",
            display_profile="puzzlescript",
        )
        renderer = dashboard.render
        event_sink = dashboard.push_event

    env = ArcadeEnv(
        game_id=args.game_id,
        backend_url=args.backend_url,
        renderer=renderer,
    )

    try:
        result = None
        total_episodes = max(1, args.episodes)
        for episode in range(1, total_episodes + 1):
            event_sink(f"episode {episode}/{total_episodes}")
            result = PerceptLiveRunner(
                env,
                goal=goal,
                model=model,
                output_path=args.output,
                max_steps=args.max_steps,
                sleep_seconds=args.sleep,
                event_sink=event_sink,
            ).run()
            print(f"episode={episode}")
            print(f"goal_reached={result.goal_reached}")
            print(f"steps={result.steps}")
        if result is not None:
            print(f"rules={result.output_path}")
            print(f"store={model.store_path}")
            print(f"journal={model.journal_path}")
    finally:
        if dashboard is not None:
            dashboard.close()


if __name__ == "__main__":
    main()
