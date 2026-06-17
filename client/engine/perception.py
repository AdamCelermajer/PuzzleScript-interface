from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from client.arc.types import FrameData, GameAction, GameState, RenderedFrame
from client.engine.utils import last_grid


Grid = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class EngineImage:
    """Optional rendered image attached to a perceived engine state."""

    mime_type: str
    data_url: str
    width: int | None = None
    height: int | None = None

    @classmethod
    def from_rendered_frame(cls, rendered_frame: RenderedFrame | None) -> "EngineImage | None":
        if rendered_frame is None or not rendered_frame.data_url:
            return None
        return cls(
            mime_type=str(rendered_frame.mime_type),
            data_url=str(rendered_frame.data_url),
            width=rendered_frame.width,
            height=rendered_frame.height,
        )

    @classmethod
    def from_data(cls, data: dict[str, Any] | None) -> "EngineImage | None":
        if not data:
            return None
        return cls(
            mime_type=str(data.get("mime_type", "")),
            data_url=str(data.get("data_url", "")),
            width=data.get("width"),
            height=data.get("height"),
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "mime_type": self.mime_type,
            "data_url": self.data_url,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class EngineState:
    """Stable perceived state used by the engine loop."""

    grid: Grid
    state: GameState
    levels_completed: int
    win_levels: int
    game_id: str
    image: EngineImage | None = field(default=None, compare=False, hash=False)
    available_actions: tuple[GameAction, ...] = field(
        default_factory=tuple, compare=False, hash=False
    )

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "EngineState":
        return cls(
            grid=tuple(tuple(int(value) for value in row) for row in data["grid"]),
            state=GameState(str(data["state"])),
            levels_completed=int(data.get("levels_completed", 0)),
            win_levels=int(data.get("win_levels", 0)),
            game_id=str(data.get("game_id", "")),
            image=EngineImage.from_data(data.get("image")),
            available_actions=tuple(
                GameAction[str(value)] for value in data.get("available_actions", [])
            ),
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "grid": [list(row) for row in self.grid],
            "state": self.state.value,
            "levels_completed": self.levels_completed,
            "win_levels": self.win_levels,
            "game_id": self.game_id,
            "image": self.image.to_data() if self.image else None,
            "available_actions": [action.name for action in self.available_actions],
        }

    def is_win(self) -> bool:
        return self.state == GameState.WIN or (
            self.win_levels > 0 and self.levels_completed >= self.win_levels
        )

    def rows(self) -> list[str]:
        return [" ".join(str(value) for value in row) for row in self.grid]

    def cell(self, x: int, y: int) -> int | None:
        if y < 0 or y >= len(self.grid):
            return None
        row = self.grid[y]
        if x < 0 or x >= len(row):
            return None
        return row[x]

    def positions(self, value: int) -> tuple[tuple[int, int], ...]:
        found: list[tuple[int, int]] = []
        for y, row in enumerate(self.grid):
            for x, cell_value in enumerate(row):
                if cell_value == value:
                    found.append((x, y))
        return tuple(found)

    def symbols(self) -> dict[int, tuple[tuple[int, int], ...]]:
        grouped: dict[int, list[tuple[int, int]]] = {}
        for y, row in enumerate(self.grid):
            for x, value in enumerate(row):
                grouped.setdefault(value, []).append((x, y))
        return {value: tuple(positions) for value, positions in grouped.items()}

    def changed_cells(self, after: "EngineState") -> tuple[dict[str, int], ...]:
        changes: list[dict[str, int]] = []
        max_height = max(len(self.grid), len(after.grid))
        for y in range(max_height):
            before_row = self.grid[y] if y < len(self.grid) else ()
            after_row = after.grid[y] if y < len(after.grid) else ()
            max_width = max(len(before_row), len(after_row))
            for x in range(max_width):
                before_value = before_row[x] if x < len(before_row) else -1
                after_value = after_row[x] if x < len(after_row) else -1
                if before_value == after_value:
                    continue
                changes.append(
                    {
                        "x": x,
                        "y": y,
                        "before": int(before_value),
                        "after": int(after_value),
                    }
                )
        return tuple(changes)


class Perception:
    """Converts ARC/PuzzleScript observations into stable engine state."""

    def perceive(self, frame_data: FrameData) -> EngineState:
        grid = tuple(tuple(int(value) for value in row) for row in last_grid(frame_data.frame))
        return EngineState(
            grid=grid,
            state=frame_data.state,
            levels_completed=int(frame_data.levels_completed),
            win_levels=int(frame_data.win_levels),
            game_id=str(frame_data.game_id),
            image=EngineImage.from_rendered_frame(frame_data.rendered_frame),
            available_actions=tuple(frame_data.available_actions or ()),
        )
