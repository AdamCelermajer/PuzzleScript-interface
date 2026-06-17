from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from client.arc.types import FrameData
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


def _reading_order(position: tuple[int, int]) -> tuple[int, int]:
    x, y = position
    return y, x


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

    def facts(
        self,
        known_target_positions: Iterable[tuple[int, int]] | None = None,
    ) -> tuple[str, ...]:
        facts: list[str] = []
        walls: list[tuple[int, int]] = []
        targets: set[tuple[int, int]] = set(known_target_positions or ())
        crates: list[tuple[int, int]] = []
        players: list[tuple[int, int]] = []

        for y, row in enumerate(self.grid):
            for x, symbol in enumerate(row):
                if symbol == "#":
                    walls.append((x, y))
                elif symbol == "P":
                    players.append((x, y))
                elif symbol == "O":
                    targets.add((x, y))
                elif symbol == "*":
                    crates.append((x, y))
                elif symbol == "@":
                    targets.add((x, y))
                    crates.append((x, y))

        for x, y in sorted(walls, key=_reading_order):
            facts.append(f"At(#,{x},{y})")

        numbered_targets = tuple(
            (f"O{index}", x, y)
            for index, (x, y) in enumerate(sorted(targets, key=_reading_order), start=1)
        )
        numbered_crates = tuple(
            (f"*{index}", x, y)
            for index, (x, y) in enumerate(sorted(crates, key=_reading_order), start=1)
        )

        for name, x, y in numbered_targets:
            facts.append(f"At({name},{x},{y})")

        for name, x, y in numbered_crates:
            facts.append(f"At({name},{x},{y})")

        for x, y in sorted(players, key=_reading_order):
            facts.append(f"At(P,{x},{y})")

        crate_positions = {(x, y) for _name, x, y in numbered_crates}
        for index, (_name, x, y) in enumerate(numbered_targets, start=1):
            if (x, y) in crate_positions:
                facts.append(f"At(@{index},{x},{y})")
                facts.append(f"At(@,{x},{y})")

        for player_x, player_y in players:
            for crate_name, crate_x, crate_y in numbered_crates:
                if abs(player_x - crate_x) + abs(player_y - crate_y) == 1:
                    facts.append(f"Adjacent(P,{crate_name})")

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

    def target_positions(self) -> set[tuple[int, int]]:
        return {
            (x, y)
            for x, y, symbol in self.required_cells
            if symbol in {"@", "O"}
        }

