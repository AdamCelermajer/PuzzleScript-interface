from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from client.engine.types import FrameData, GameAction
from client.engine.utils import last_grid


Position = tuple[int, int]

LEVEL1_TARGETS: frozenset[Position] = frozenset({(2, 1), (1, 3)})

ACTION_DELTAS: dict[GameAction, Position] = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}

DIRECTION_NAMES: dict[GameAction, str] = {
    GameAction.ACTION1: "UP",
    GameAction.ACTION2: "DOWN",
    GameAction.ACTION3: "LEFT",
    GameAction.ACTION4: "RIGHT",
}


def add_pos(left: Position, right: Position) -> Position:
    return left[0] + right[0], left[1] + right[1]


@dataclass(frozen=True)
class BoardState:
    width: int
    height: int
    walls: frozenset[Position]
    targets: frozenset[Position]
    crates: frozenset[Position]
    player: Position

    @classmethod
    def from_grid(cls, grid: list[list[int]]) -> "BoardState":
        walls: set[Position] = set()
        targets: set[Position] = set(LEVEL1_TARGETS)
        crates: set[Position] = set()
        player: Position | None = None

        for y, row in enumerate(grid):
            for x, value in enumerate(row):
                position = (x, y)
                if value == 1:
                    walls.add(position)
                elif value == 2:
                    player = position
                elif value == 3:
                    crates.add(position)
                elif value == 4:
                    crates.add(position)
                    targets.add(position)
                elif value == 5:
                    targets.add(position)

        if player is None:
            raise ValueError("Sokoban board frame does not contain a player")

        width = max((len(row) for row in grid), default=0)
        return cls(
            width=width,
            height=len(grid),
            walls=frozenset(walls),
            targets=frozenset(targets),
            crates=frozenset(crates),
            player=player,
        )

    @classmethod
    def from_frame_data(cls, frame_data: FrameData) -> "BoardState":
        return cls.from_grid(last_grid(frame_data.frame))

    def with_changes(
        self,
        *,
        player: Position | None = None,
        crates: frozenset[Position] | None = None,
    ) -> "BoardState":
        return BoardState(
            width=self.width,
            height=self.height,
            walls=self.walls,
            targets=self.targets,
            crates=self.crates if crates is None else crates,
            player=self.player if player is None else player,
        )

    def is_goal(self) -> bool:
        return LEVEL1_TARGETS.issubset(self.crates)

    def is_inside(self, position: Position) -> bool:
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height

    def is_blocked(self, position: Position) -> bool:
        return (
            not self.is_inside(position)
            or position in self.walls
            or position in self.crates
        )

    def cell_at(self, position: Position) -> str:
        if position == self.player:
            return "player"
        if position in self.crates and position in self.targets:
            return "crate_on_target"
        if position in self.crates:
            return "crate"
        if position in self.walls:
            return "wall"
        if position in self.targets:
            return "target"
        return "empty"

    def to_grid(self) -> list[list[int]]:
        grid: list[list[int]] = []
        for y in range(self.height):
            row: list[int] = []
            for x in range(self.width):
                position = (x, y)
                if position == self.player:
                    row.append(2)
                elif position in self.crates and position in self.targets:
                    row.append(4)
                elif position in self.crates:
                    row.append(3)
                elif position in self.walls:
                    row.append(1)
                elif position in self.targets:
                    row.append(5)
                else:
                    row.append(0)
            grid.append(row)
        return grid

    def facts(self) -> set[str]:
        facts: set[str] = {f"At(Player,{self.player[0]},{self.player[1]})"}
        facts.update(_position_facts("Wall", self.walls))
        facts.update(_position_facts("Target", self.targets))
        facts.update(_position_facts("At(Crate", self.crates, suffix=")"))

        for y in range(self.height):
            for x in range(self.width):
                position = (x, y)
                if self.cell_at(position) in {"empty", "target"}:
                    facts.add(f"Empty({x},{y})")
                if position in self.crates or position == self.player:
                    facts.add(f"Occupied({x},{y})")

        for action, delta in ACTION_DELTAS.items():
            direction = DIRECTION_NAMES[action]
            for y in range(self.height):
                for x in range(self.width):
                    neighbor = add_pos((x, y), delta)
                    if self.is_inside(neighbor):
                        facts.add(
                            f"Adjacent(({x},{y}),{direction},({neighbor[0]},{neighbor[1]}))"
                        )
        return facts

    def apply_sokoban_action(self, action: GameAction) -> "BoardState":
        delta = ACTION_DELTAS.get(action)
        if delta is None:
            return self

        front = add_pos(self.player, delta)
        if front in self.walls or not self.is_inside(front):
            return self

        if front in self.crates:
            behind = add_pos(front, delta)
            if self.is_blocked(behind):
                return self
            crates = set(self.crates)
            crates.remove(front)
            crates.add(behind)
            return self.with_changes(player=front, crates=frozenset(crates))

        return self.with_changes(player=front)


def _position_facts(
    name: str, positions: Iterable[Position], *, suffix: str = ""
) -> set[str]:
    if name == "At(Crate":
        return {f"At(Crate,{x},{y}{suffix}" for x, y in positions}
    return {f"{name}({x},{y})" for x, y in positions}
