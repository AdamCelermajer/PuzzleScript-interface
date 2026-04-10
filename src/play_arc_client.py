from __future__ import annotations

import argparse
import os
import sys

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState


QUIT_COMMAND = "quit"


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


def print_help(game_id: str) -> None:
    print(f"Game: {game_id}")
    print("Controls: W/A/S/D move | R reset | Z undo | Q quit")


def print_state(obs) -> None:
    if obs is None:
        print("No observation returned.")
        return
    print(
        f"State: {obs.state.name} | Levels completed: {obs.levels_completed}/{obs.win_levels}"
    )
    if obs.state == GameState.WIN:
        print("You won. Press R to play again or Q to quit.")
    elif obs.state == GameState.GAME_OVER:
        print("Game over. Press R to reset or Q to quit.")


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
    env = arcade.make(args.game_id, render_mode="terminal-fast")
    if env is None:
        print(f"Failed to create game environment for {args.game_id}", file=sys.stderr)
        return 1

    print_help(args.game_id)
    obs = env.reset()
    print_state(obs)

    while True:
        key = read_key()
        command = key_to_action(key)
        if command is None:
            continue
        if command == QUIT_COMMAND:
            print("Bye.")
            return 0

        if command == GameAction.RESET:
            obs = env.reset()
        else:
            obs = env.step(command)
        print_state(obs)


if __name__ == "__main__":
    raise SystemExit(main())
