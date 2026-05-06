from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from client.engine.types import FrameData
from client.engine.utils import last_grid


Cell = tuple[int, int, int]
CellChange = tuple[int, int, int, int]


@dataclass(frozen=True)
class RawFrame:
    """Final rendered integer grid, with no object names attached."""

    grid: tuple[tuple[int, ...], ...]

    @classmethod
    def from_grid(cls, grid: Sequence[Sequence[int]]) -> "RawFrame":
        return cls(tuple(tuple(int(value) for value in row) for row in grid))

    @classmethod
    def from_frame_data(cls, frame_data: FrameData) -> "RawFrame":
        return cls.from_grid(last_grid(frame_data.frame))

    @property
    def width(self) -> int:
        return max((len(row) for row in self.grid), default=0)

    @property
    def height(self) -> int:
        return len(self.grid)

    def cell(self, x: int, y: int) -> int | None:
        if y < 0 or y >= len(self.grid):
            return None
        row = self.grid[y]
        if x < 0 or x >= len(row):
            return None
        return row[x]

    def changed_cells(self, other: "RawFrame") -> tuple[CellChange, ...]:
        changes: list[CellChange] = []
        height = max(self.height, other.height)
        width = max(self.width, other.width)
        for y in range(height):
            for x in range(width):
                before = self.cell(x, y)
                after = other.cell(x, y)
                if before != after:
                    changes.append(
                        (
                            x,
                            y,
                            -1 if before is None else before,
                            -1 if after is None else after,
                        )
                    )
        return tuple(changes)

    def apply_changes(self, changes: Iterable[CellChange]) -> "RawFrame" | None:
        rows = [list(row) for row in self.grid]
        for x, y, before, after in changes:
            if self.cell(x, y) != before:
                return None
            if y < 0 or x < 0 or y >= len(rows) or x >= len(rows[y]):
                return None
            rows[y][x] = after
        return RawFrame.from_grid(rows)

    def positions(self, value: int) -> tuple[tuple[int, int], ...]:
        positions = []
        for y, row in enumerate(self.grid):
            for x, cell_value in enumerate(row):
                if cell_value == value:
                    positions.append((x, y))
        return tuple(positions)

    def line(
        self, x: int, y: int, dx: int, dy: int, length: int
    ) -> tuple[int, ...] | None:
        values = []
        for index in range(length):
            value = self.cell(x + dx * index, y + dy * index)
            if value is None:
                return None
            values.append(value)
        return tuple(values)

    def apply_line(
        self,
        x: int,
        y: int,
        dx: int,
        dy: int,
        after_values: Iterable[int],
    ) -> "RawFrame" | None:
        rows = [list(row) for row in self.grid]
        for index, value in enumerate(after_values):
            cx = x + dx * index
            cy = y + dy * index
            if cy < 0 or cy >= len(rows) or cx < 0 or cx >= len(rows[cy]):
                return None
            rows[cy][cx] = int(value)
        return RawFrame.from_grid(rows)

    def changed_positions(self, other: "RawFrame") -> tuple[tuple[int, int], ...]:
        return tuple((x, y) for x, y, _before, _after in self.changed_cells(other))

    def to_lines(self) -> list[str]:
        if not self.grid:
            return ["[]"]
        return [" ".join(str(value) for value in row) for row in self.grid]


@dataclass(frozen=True)
class RawGoal:
    """Goal expressed only as required raw cell values."""

    required_cells: tuple[Cell, ...]

    def is_satisfied(self, frame: RawFrame) -> bool:
        return all(frame.cell(x, y) == value for x, y, value in self.required_cells)

    @classmethod
    def from_cells(cls, cells: Iterable[Sequence[int]]) -> "RawGoal":
        return cls(tuple((int(x), int(y), int(value)) for x, y, value in cells))

    def to_markdown(self) -> str:
        if not self.required_cells:
            return "- No required raw cells."
        return "\n".join(
            f"- cell({x},{y}) == {value}" for x, y, value in self.required_cells
        )
