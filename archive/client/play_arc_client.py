from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

from client.terminal_dashboard import TerminalDashboard


QUIT_COMMAND = "quit"
CLICK_COMMAND = "click"
COORDINATE_CLICK_COMMAND = "coordinate_click"
CONTROLS_TEXT = "W/A/S/D move | mouse click board | C coordinate click | R reset | Z undo | Q quit"
SGR_MOUSE_RE = re.compile(r"\x1b\[<(?P<button>\d+);(?P<x>\d+);(?P<y>\d+)(?P<kind>[mM])")


def enable_windows_vt_input() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0200)
    except Exception:
        pass


def key_to_action(key: str) -> GameAction | str | None:
    normalized = (key or "").lower()
    if not normalized:
        return None

    mapping = {
        "w": GameAction.ACTION1,
        "a": GameAction.ACTION3,
        "s": GameAction.ACTION2,
        "d": GameAction.ACTION4,
        " ": GameAction.ACTION5,
        "r": GameAction.RESET,
        "z": GameAction.ACTION7,
        "c": COORDINATE_CLICK_COMMAND,
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
            if key == "\x1b":
                time.sleep(0.01)
                chars = [key]
                while msvcrt.kbhit():
                    chars.append(msvcrt.getwch())
                return "".join(chars)
            return key

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x1b":
            chars = [key]
            while select.select([sys.stdin], [], [], 0.01)[0]:
                chars.append(sys.stdin.read(1))
            return "".join(chars)
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def mouse_position_from_key(key: str) -> tuple[int, int] | None:
    match = SGR_MOUSE_RE.fullmatch(key or "")
    if not match or match.group("kind") != "M":
        return None
    button = int(match.group("button"))
    if button != 0:
        return None
    return int(match.group("x")), int(match.group("y"))


def action_is_available(obs, action: GameAction) -> bool:
    available_actions = getattr(obs, "available_actions", []) or []
    for available in available_actions:
        if available == action:
            return True
        if getattr(available, "name", "") == action.name:
            return True
        if str(available) == action.name:
            return True
        try:
            if int(available) == int(action.value):
                return True
        except (TypeError, ValueError):
            pass
    return False


def read_coordinate_click() -> dict[str, int] | None:
    text = input("ACTION6 coordinate click as x y: ").strip()
    parts = text.replace(",", " ").split()
    if len(parts) != 2:
        return None
    try:
        return {"x": int(parts[0]), "y": int(parts[1])}
    except ValueError:
        return None


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
            "Use W/A/S/D, mouse click for ACTION6, C for coordinate click, R reset, Z undo, Q quit."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Play a local ARC-compatible PuzzleScript game from the terminal"
    )
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.getenv("ARC_API_KEY", "local-dev"))
    args = parser.parse_args()
    enable_windows_vt_input()

    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=args.backend_url,
        arc_api_key=args.api_key,
    )
    dashboard = TerminalDashboard(
        game_id=args.game_id,
        mode="PLAY",
        controls=CONTROLS_TEXT,
        display_profile="color",
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
            mouse_position = mouse_position_from_key(key)
            if mouse_position is not None:
                cell = dashboard.click_cell_from_terminal_position(*mouse_position)
                if cell is None:
                    continue
                if not action_is_available(obs, GameAction.ACTION6):
                    dashboard.push_event("Mouse click ignored: ACTION6 unavailable")
                    continue
                data = {"x": cell[0], "y": cell[1]}
                dashboard.push_event(f"Mouse click: ACTION6 {data}")
                obs = env.step(GameAction.ACTION6, data=data)
                update_dashboard(dashboard, obs)
                continue

            command = key_to_action(key)
            if command is None:
                continue
            if command == QUIT_COMMAND:
                dashboard.close()
                print("Bye.")
                return 0
            if command == COORDINATE_CLICK_COMMAND:
                if not action_is_available(obs, GameAction.ACTION6):
                    dashboard.push_event("Coordinate click ignored: ACTION6 unavailable")
                    continue
                dashboard.close()
                data = read_coordinate_click()
                update_dashboard(dashboard, obs)
                if data is None:
                    dashboard.push_event("Coordinate click cancelled")
                    continue
                dashboard.push_event(f"Coordinate click: ACTION6 {data}")
                obs = env.step(GameAction.ACTION6, data=data)
                update_dashboard(dashboard, obs)
                continue

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
