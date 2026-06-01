from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tkinter as tk

from arc_agi import Arcade, OperationMode
from arc_agi.rendering import COLOR_MAP
from arcengine import GameAction, GameState

from client.engine.utils import last_grid
from client.play_arc_client import action_is_available


ORIGIN_X = 48
ORIGIN_Y = 48


def cell_size_for_grid(
    columns: int,
    rows: int,
    *,
    max_width: int = 960,
    max_height: int = 720,
) -> int:
    if columns <= 0 or rows <= 0:
        return 16
    return max(8, min(24, max_width // columns, max_height // rows))


def cell_from_pixel(
    *,
    pixel_x: int,
    pixel_y: int,
    columns: int,
    rows: int,
    cell_size: int,
    origin_x: int = ORIGIN_X,
    origin_y: int = ORIGIN_Y,
) -> tuple[int, int] | None:
    if pixel_x < origin_x or pixel_y < origin_y:
        return None
    x = (pixel_x - origin_x) // cell_size
    y = (pixel_y - origin_y) // cell_size
    if x < 0 or y < 0 or x >= columns or y >= rows:
        return None
    return x, y


def normalize_color(value: int) -> str:
    color = COLOR_MAP.get(int(value), "#000000FF")
    return color[:7]


def game_action_from_key(key: str) -> GameAction | None:
    mapping = {
        "w": GameAction.ACTION1,
        "s": GameAction.ACTION2,
        "a": GameAction.ACTION3,
        "d": GameAction.ACTION4,
        " ": GameAction.ACTION5,
        "r": GameAction.RESET,
        "z": GameAction.ACTION7,
    }
    return mapping.get(key)


class ArcGuiPlayer:
    def __init__(self, game_id: str, backend_url: str, api_key: str) -> None:
        self.game_id = game_id
        self.backend_url = backend_url
        self.api_key = api_key
        self.arcade = Arcade(
            operation_mode=OperationMode.ONLINE,
            arc_base_url=backend_url,
            arc_api_key=api_key,
        )
        self.env = self.arcade.make(game_id)
        if self.env is None:
            raise RuntimeError(f"Failed to create game environment for {game_id}")

        self.root = tk.Tk()
        self.root.title(f"ARC player - {game_id}")
        self.status = tk.StringVar(value="Loading...")
        self.canvas = tk.Canvas(self.root, background="#202020", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        tk.Label(self.root, textvariable=self.status, anchor="w").pack(fill=tk.X)
        self.obs: Any = None
        self.grid: list[list[int]] = []
        self.cell_size = 16

        self.canvas.bind("<Button-1>", self.on_click)
        self.root.bind("<Key>", self.on_key)
        self.reset()

    def reset(self) -> None:
        self.obs = self.env.reset()
        self.redraw()

    def step(self, action: GameAction, data: dict | None = None) -> None:
        self.obs = self.env.step(action, data=data)
        self.redraw()

    def redraw(self) -> None:
        self.grid = last_grid(getattr(self.obs, "frame", []) or [])
        rows = len(self.grid)
        columns = max((len(row) for row in self.grid), default=0)
        self.cell_size = cell_size_for_grid(columns, rows)
        width = ORIGIN_X + columns * self.cell_size + 24
        height = ORIGIN_Y + rows * self.cell_size + 24
        self.canvas.config(width=width, height=height)
        self.canvas.delete("all")
        self.draw_axes(columns, rows)
        for y, row in enumerate(self.grid):
            for x, value in enumerate(row):
                left = ORIGIN_X + x * self.cell_size
                top = ORIGIN_Y + y * self.cell_size
                self.canvas.create_rectangle(
                    left,
                    top,
                    left + self.cell_size,
                    top + self.cell_size,
                    fill=normalize_color(int(value)),
                    outline="#303030",
                )
        self.status.set(self.status_text())

    def draw_axes(self, columns: int, rows: int) -> None:
        for x in range(columns):
            if x % 5 == 0 or columns <= 20:
                left = ORIGIN_X + x * self.cell_size
                self.canvas.create_text(
                    left + self.cell_size / 2,
                    ORIGIN_Y - 16,
                    text=str(x),
                    fill="#e8e8e8",
                    font=("Consolas", 8),
                )
        for y in range(rows):
            if y % 5 == 0 or rows <= 20:
                top = ORIGIN_Y + y * self.cell_size
                self.canvas.create_text(
                    ORIGIN_X - 18,
                    top + self.cell_size / 2,
                    text=str(y),
                    fill="#e8e8e8",
                    font=("Consolas", 8),
                )

    def status_text(self) -> str:
        state = getattr(getattr(self.obs, "state", None), "name", "UNKNOWN")
        levels = getattr(self.obs, "levels_completed", 0)
        win_levels = getattr(self.obs, "win_levels", 0)
        actions = [
            getattr(action, "name", str(action))
            for action in getattr(self.obs, "available_actions", []) or []
        ]
        return (
            f"{state} | levels {levels}/{win_levels} | actions {actions} | "
            "click board for ACTION6, WASD move, Space action, R reset, Z undo, Q quit"
        )

    def on_click(self, event: Any) -> None:
        rows = len(self.grid)
        columns = max((len(row) for row in self.grid), default=0)
        cell = cell_from_pixel(
            pixel_x=int(event.x),
            pixel_y=int(event.y),
            columns=columns,
            rows=rows,
            cell_size=self.cell_size,
        )
        if cell is None:
            return
        if not action_is_available(self.obs, GameAction.ACTION6):
            self.status.set("ACTION6 is not available in this state")
            return
        self.step(GameAction.ACTION6, data={"x": cell[0], "y": cell[1]})

    def on_key(self, event: Any) -> None:
        key = str(getattr(event, "char", "") or "").lower()
        if key == "q":
            self.root.destroy()
            return
        action = game_action_from_key(key)
        if action is None:
            return
        if action == GameAction.RESET:
            self.reset()
            return
        if not action_is_available(self.obs, action):
            self.status.set(f"{action.name} is not available in this state")
            return
        self.step(action)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Play an ARC game in a mouse GUI.")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--backend-url", default="https://three.arcprize.org")
    parser.add_argument("--api-key", default=os.getenv("ARC_API_KEY", ""))
    args = parser.parse_args()

    player = ArcGuiPlayer(args.game_id, args.backend_url, args.api_key)
    player.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
