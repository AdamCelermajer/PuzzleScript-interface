"""Modality (ps_modality-v1): the game's true rules, the shortest solution of each level, and a
replay that reconstructs the real state after every action of a recorded run.

The rules are the four RULES lines of the game's script.txt, with Nonblack = White or Grey:

    [ > Player Nonblack | Crate Nonblack ] -> [ > Player Nonblack | > Crate Nonblack ]
    [ > Player Black | Crate Black ]       -> [ > Player Black | > Crate Black ]
    [ > Player White | Black ] -> CANCEL
    [ > Player Black | White ] -> CANCEL

and "All Crate on Target" wins. Undo, restart and level loading follow the runtime
(node_modules/puzzlescript/lib/engine.js and puzzlescript_interface/runtime/server.js): the engine
snapshots the board before every move, even one that changes nothing; ACTION7 restores the last
snapshot but never goes past the level's start; RESET reloads the level and clears the undo
history; a win loads the next level within the same action.

    python -m studies.thursday.modality            optimum per level, then validate the 20 Oct rollouts
    python -m studies.thursday.modality RUN [RUN]  validate the given run folders
"""
from __future__ import annotations

import json
import sys
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "puzzlescript_interface" / "games" / "ps_modality-v1" / "script.txt"
ROLLOUTS = ROOT / "output/workbench/20261020T142237-modality-harness2-27b-agent-d099cb74/run-0001/rollouts"
DEFAULT_RUNS = [ROLLOUTS / name for name in ("base1", "inv1", "dom1", "agg1", "final")]

# Floor colour under each level character (legend of script.txt): W white, B dark ("Black"), G grey.
FLOOR = {".": "B", "+": "W", "g": "G", "p": "B", "q": "W", "*": "B", "@": "W", "t": "B", "u": "W"}
MOVES = {"ACTION1": (-1, 0), "ACTION2": (1, 0), "ACTION3": (0, -1), "ACTION4": (0, 1)}
# Outcomes of a move that leave the board unchanged.
BLOCKED = ("edge", "white_dark", "wrong_floor_push", "push_edge")

Cell = tuple[int, int]


@dataclass(frozen=True)
class Level:
    floor: tuple[str, ...]  # one string per row, "W"/"B"/"G" per cell
    player: Cell
    box: Cell
    target: Cell

    def inside(self, cell: Cell) -> bool:
        return 0 <= cell[0] < len(self.floor) and 0 <= cell[1] < len(self.floor[0])

    def at(self, cell: Cell) -> str:
        return self.floor[cell[0]][cell[1]]


@lru_cache(maxsize=1)
def levels() -> tuple[Level, ...]:
    rows_of: list[list[str]] = []
    current: list[str] = []
    for line in SCRIPT.read_text(encoding="utf-8").split("LEVELS", 1)[1].splitlines():
        text = line.strip().lower()
        if not text or text.startswith("="):
            if current:
                rows_of.append(current)
                current = []
            continue
        current.append(text)
    if current:
        rows_of.append(current)
    parsed = []
    for rows in rows_of:
        found = {}
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch in "pq":
                    found["player"] = (r, c)
                if ch in "*@":
                    found["box"] = (r, c)
                if ch in "tu":
                    found["target"] = (r, c)
        parsed.append(Level(tuple("".join(FLOOR[ch] for ch in row) for row in rows), **found))
    return tuple(parsed)


def step(level: Level, player: Cell, box: Cell, action: str) -> tuple[str, Cell, Cell]:
    """One move under the true rules: (kind, player, box).

    kind is "move" or "push" when the board changes; otherwise "edge" (the player would leave the
    board), "white_dark" (a step between white and dark, cancelled), "wrong_floor_push" (the box
    is not pushable from this floor) or "push_edge" (the box would leave the board).
    """
    dr, dc = MOVES[action]
    nxt = (player[0] + dr, player[1] + dc)
    if not level.inside(nxt):
        return "edge", player, box
    here = level.at(player)
    if nxt == box:
        there = level.at(box)
        if (here in "WG" and there in "WG") or (here == "B" and there == "B"):
            beyond = (box[0] + dr, box[1] + dc)
            if not level.inside(beyond):
                return "push_edge", player, box
            return "push", nxt, beyond
        return "wrong_floor_push", player, box
    if {here, level.at(nxt)} == {"W", "B"}:
        return "white_dark", player, box
    return "move", nxt, box


@lru_cache(maxsize=None)
def optimum(index: int) -> tuple[str, ...]:
    """Shortest action sequence that solves level ``index`` (0-based), by breadth-first search."""
    level = levels()[index]
    start = (level.player, level.box)
    previous: dict[tuple[Cell, Cell], tuple | None] = {start: None}
    queue = deque([start])
    while queue:
        state = queue.popleft()
        if state[1] == level.target:
            path = []
            while previous[state] is not None:
                state, action = previous[state]
                path.append(action)
            return tuple(reversed(path))
        for action in MOVES:
            kind, player, box = step(level, *state, action)
            if kind in ("move", "push") and (player, box) not in previous:
                previous[(player, box)] = (state, action)
                queue.append((player, box))
    raise ValueError(f"level {index + 1} has no solution")


def optimum_moves() -> list[int]:
    return [len(optimum(i)) for i in range(len(levels()))]


@dataclass
class Step:
    index: int  # 1-based action number, as action_index in transitions.jsonl
    action: str
    level: int  # 0-based level the action was taken in
    kind: str  # a step() kind, or "undo", "undo_empty", "reset", "other"
    changed: bool
    won: bool  # this action completed the level
    levels_completed: int  # after the action
    player: Cell  # after the action
    box: Cell


def replay(actions: list[str]) -> list[Step]:
    """The true state after every action of a run, from the start of level 1."""
    table = levels()
    index = 0
    level = table[0]
    player, box = level.player, level.box
    undo = [(player, box)]
    out: list[Step] = []
    for n, action in enumerate(actions, 1):
        before, taken_in, won = (player, box), index, False
        if action in MOVES:
            undo.append(before)  # the engine snapshots before every move
            kind, player, box = step(level, player, box, action)
            if box == level.target:
                won, index = True, index + 1
                if index < len(table):
                    level = table[index]
                    player, box = level.player, level.box
                    undo = [(player, box)]
        elif action == "ACTION7":
            snapshot = undo.pop()
            if undo:
                kind, (player, box) = "undo", snapshot
            else:
                kind = "undo_empty"
                undo.append(snapshot)
        elif action == "RESET":
            kind, player, box = "reset", level.player, level.box
            undo = [(player, box)]
        else:
            kind = "other"
        out.append(Step(n, action, taken_in, kind, won or (player, box) != before, won, index, player, box))
    return out


def load_transitions(run: Path) -> list[dict]:
    path = run / "transitions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate(run: Path) -> list[str]:
    """Mismatches between the replay and the run's recorded transitions (empty when they agree).

    Checks, at every action, the changed flag and the levels completed, and, for actions that do
    not complete a level, that the cells whose player/box occupancy changed are exactly the cells
    the run recorded as changed.
    """
    transitions = load_transitions(run)
    steps = replay([t["action"] for t in transitions])
    problems = []
    player, box = levels()[0].player, levels()[0].box
    for t, s in zip(transitions, steps):
        recorded = (bool(t["changed"]), int(t["after"]["levels_completed"]))
        if recorded != (s.changed, s.levels_completed):
            problems.append(f"action {t['action_index']} {t['action']}: recorded changed={recorded[0]} "
                            f"levels={recorded[1]}, replay changed={s.changed} levels={s.levels_completed} ({s.kind})")
        elif not s.won:
            occupant = lambda cell, p, b: "player" if cell == p else "box" if cell == b else ""
            moved = {cell for cell in {player, box, s.player, s.box}
                     if occupant(cell, player, box) != occupant(cell, s.player, s.box)}
            cells = {(c["row"], c["col"]) for c in t.get("changed_cells", [])}
            if moved != cells:
                problems.append(f"action {t['action_index']} {t['action']}: recorded cells {sorted(cells)}, "
                                f"replay cells {sorted(moved)} ({s.kind})")
        player, box = s.player, s.box
    return problems


def main(argv: list[str]) -> int:
    print("optimum moves per level:", optimum_moves())
    failed = 0
    for run in [Path(a) for a in argv] or DEFAULT_RUNS:
        problems = validate(run)
        failed += bool(problems)
        print(f"{run.name}: {len(load_transitions(run))} actions, "
              + ("replay matches" if not problems else f"{len(problems)} mismatches"))
        for problem in problems[:10]:
            print("   ", problem)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
