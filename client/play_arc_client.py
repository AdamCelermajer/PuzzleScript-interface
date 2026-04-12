from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

from client.terminal_dashboard import TerminalDashboard


QUIT_COMMAND = "quit"
CONTROLS_TEXT = "W/A/S/D move | R reset | Z undo | Q quit"


def key_to_action(key: str) -> GameAction | str | None:
    normalized = (key or "").strip().lower()
    if not normalized:
        return None

    mapping = {
        "w": GameAction.ACTION1,
        "a": GameAction.ACTION3,
        "s": GameAction.ACTION2,
        "d": GameAction.ACTION4,
        "r": GameAction.RESET,
        "z": GameAction.ACTION7,
        "q": QUIT_COMMAND,
    }
    return mapping.get(normalized)


def read_key() -> str:
    if os.name == "nt":
        import msvcrt

        while True:
            key = msvcrt.getwch()
            if key in {"\x00", "\xe0"}:
                msvcrt.getwch()
                continue
            return key

    import termios
    import tty

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def update_dashboard(dashboard: TerminalDashboard, obs) -> None:
    if obs is None:
        dashboard.set_status("No observation returned.")
        return
    dashboard.set_status(
        f"State: {obs.state.name} | Levels completed: {obs.levels_completed}/{obs.win_levels}"
    )
    if obs.state == GameState.WIN:
        dashboard.set_detail("You won. Press R to play again or Q to quit.")
    elif obs.state == GameState.GAME_OVER:
        dashboard.set_detail("Game over. Press R to reset or Q to quit.")
    else:
        dashboard.set_detail(
            "Use W/A/S/D to move. Press R to reset, Z to undo, Q to quit."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Play a local ARC-compatible PuzzleScript game from the terminal"
    )
    parser.add_argument("--game-id", default="sokoban-basic-v1")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="local-dev")
    args = parser.parse_args()

    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=args.backend_url,
        arc_api_key=args.api_key,
    )
    dashboard = TerminalDashboard(
        game_id=args.game_id,
        mode="PLAY",
        controls=CONTROLS_TEXT,
    )

    try:
        env = arcade.make(args.game_id, renderer=dashboard.render)
        if env is None:
            print(
                f"Failed to create game environment for {args.game_id}", file=sys.stderr
            )
            return 1

        dashboard.push_event(f"Loaded game {args.game_id}")
        obs = env.reset()
        update_dashboard(dashboard, obs)

        while True:
            key = read_key()
            command = key_to_action(key)
            if command is None:
                continue
            if command == QUIT_COMMAND:
                dashboard.close()
                print("Bye.")
                return 0

            if command == GameAction.RESET:
                dashboard.push_event("Requested reset")
                obs = env.reset()
            else:
                dashboard.push_event(f"Input: {command.name}")
                obs = env.step(command)
            update_dashboard(dashboard, obs)
    finally:
        dashboard.close()


if __name__ == "__main__":
    raise SystemExit(main())
