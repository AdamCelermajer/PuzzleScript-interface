from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from client.engine.types import FrameData
from client.engine.utils import last_grid


DEFAULT_SYMBOL_MAP: dict[int, str] = {
    0: ".",
    1: "#",
    2: "P",
    3: "*",
    4: "@",
    5: "O",
    6: "?",
}

SymbolCell = tuple[int, int, str]


@dataclass(frozen=True)
class SymbolFrame:
    """Grid represented as PuzzleScript display symbols, not human object names."""

    grid: tuple[tuple[str, ...], ...]

    @classmethod
    def from_rows(cls, rows: Sequence[str]) -> "SymbolFrame":
        return cls(tuple(tuple(row) for row in rows))

    @classmethod
    def from_grid(
        cls, grid: Sequence[Sequence[int]], symbol_map: dict[int, str] | None = None
    ) -> "SymbolFrame":
        mapping = symbol_map or DEFAULT_SYMBOL_MAP
        return cls(
            tuple(
                tuple(mapping.get(int(value), "?") for value in row)
                for row in grid
            )
        )

    @classmethod
    def from_frame_data(
        cls, frame_data: FrameData, symbol_map: dict[int, str] | None = None
    ) -> "SymbolFrame":
        return cls.from_grid(last_grid(frame_data.frame), symbol_map)

    @property
    def width(self) -> int:
        return max((len(row) for row in self.grid), default=0)

    @property
    def height(self) -> int:
        return len(self.grid)

    def cell(self, x: int, y: int) -> str | None:
        if y < 0 or y >= len(self.grid):
            return None
        row = self.grid[y]
        if x < 0 or x >= len(row):
            return None
        return row[x]

    def positions(self, symbol: str) -> tuple[tuple[int, int], ...]:
        found = []
        for y, row in enumerate(self.grid):
            for x, value in enumerate(row):
                if value == symbol:
                    found.append((x, y))
        return tuple(found)

    def line(self, x: int, y: int, dx: int, dy: int, length: int) -> tuple[str, ...] | None:
        values: list[str] = []
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
        after_symbols: Sequence[str],
    ) -> "SymbolFrame" | None:
        rows = [list(row) for row in self.grid]
        for index, symbol in enumerate(after_symbols):
            cx = x + dx * index
            cy = y + dy * index
            if cy < 0 or cy >= len(rows) or cx < 0 or cx >= len(rows[cy]):
                return None
            rows[cy][cx] = symbol
        return SymbolFrame(tuple(tuple(row) for row in rows))

    def facts(self) -> tuple[str, ...]:
        facts: list[str] = []
        for y, row in enumerate(self.grid):
            for x, symbol in enumerate(row):
                if symbol == ".":
                    facts.append(f"Empty({x},{y})")
                else:
                    facts.append(f"At({symbol},{x},{y})")
                facts.append(f"InBounds({x},{y})")
                for nx, ny in ((x + 1, y), (x, y + 1)):
                    if self.cell(nx, ny) is not None:
                        facts.append(f"Adjacent({x},{y},{nx},{ny})")
                        facts.append(f"Adjacent({nx},{ny},{x},{y})")
        return tuple(facts)

    def changed_positions(self, other: "SymbolFrame") -> tuple[tuple[int, int], ...]:
        changes = []
        for y in range(max(self.height, other.height)):
            for x in range(max(self.width, other.width)):
                if self.cell(x, y) != other.cell(x, y):
                    changes.append((x, y))
        return tuple(changes)

    def to_rows(self) -> list[str]:
        return ["".join(row) for row in self.grid]


@dataclass(frozen=True)
class SymbolGoal:
    required_cells: tuple[SymbolCell, ...]

    @classmethod
    def from_cells(cls, cells: Iterable[Sequence[object]]) -> "SymbolGoal":
        return cls(tuple((int(x), int(y), str(symbol)) for x, y, symbol in cells))

    def is_satisfied(self, frame: SymbolFrame) -> bool:
        return all(
            self._cell_satisfies(frame.cell(x, y), symbol)
            for x, y, symbol in self.required_cells
        )

    def _cell_satisfies(self, actual: str | None, required: str) -> bool:
        if required == "*":
            return actual in {"*", "@"}
        return actual == required

    def to_markdown(self) -> str:
        if not self.required_cells:
            return "- No required symbol cells."
        return "\n".join(
            f"- At({symbol},{x},{y})" for x, y, symbol in self.required_cells
        )

