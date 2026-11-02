# Your notes from a previous game

You played this game before. At the end of that game you wrote the notes below.

# World model — "tile robot pushes a door onto the goal" puzzle

The game is a Sokoban-like sliding puzzle played on small grids (3x5, 5x5, 6x6,
9x11 for levels 1-4). There is a robot, a door, a goal tile, and floor tiles.
The objective of every level is to **push the door onto the goal (blue) tile**,
which instantly completes the level and loads the next one.

You can only affect the world by issuing opaque actions; everything below is
inferred from observed `do` outputs. Each level is independent; completing one
loads a fresh, larger grid.

---

## Commands

| Command | Effect | Cost |
|---|---|---|
| `python game.py look` | print current grid + status; save picture as `frame.png` | free |
| `python game.py do ACTION{n}` | take one game action | 1 action |
| `python game.py reset` | restart current level | 1 action |

`available_actions` is always `ACTION1, ACTION2, ACTION3, ACTION4, ACTION7`.
Initial budget for the run: **200 actions** (shared across all levels).

### What each action does (all CONFIRMED)
- `ACTION1` = move the robot **up**
- `ACTION2` = move the robot **down**
- `ACTION3` = move the robot **left**
- `ACTION4` = move the robot **right**
- `ACTION7` = **undo** the immediately preceding move (restores the exact
  previous grid state). It is not a fixed direction.

A move "succeeds" when the cell(s) change; it is reported as
`changed <cell> <old>-><new> ...`. When the robot tries an illegal move the
command prints `nothing changed` and the grid is unchanged (but the action was
still consumed). A successful level-ending push prints `LEVEL COMPLETED (k/4)`.

---

## Objects (tile codes)

Each grid cell has a fixed **base tile** (the floor). The robot and the door
stand *on top of* a base tile; a cell then displays a **composite code**
("sprite + base tile"). Observed codes:

| code | meaning |
|---|---|
| `0` | goal tile (blue square) — levels 1-3 |
| `9` | goal tile (blue square) — appears in level 4 |
| `1` | white floor |
| `2` | dark floor |
| `4` | checker (grey) floor — the only bridge between white and dark zones |
| `3` | door standing on a **white** base |
| `8` | door standing on a **dark** base |
| `10` | door standing on a **checker** base |
| `5` | robot standing on a **dark** base |
| `6` | robot standing on a **checker** base |
| `7` | robot standing on a **white** base **or on the goal** |

Key model fact (CONFIRMED): the base tile is a property of the *cell*, not an
item the robot carries. When the robot moves X->Y, cell X simply re-exposes its
base and the robot's display becomes "robot-on-base(Y)". The door likewise just
stands on whatever base it currently occupies. No floors are re-ordered.

Note `7` is used for both "robot on white" and "robot on goal", so the goal
behaves like a walkable floor for the robot.

---

## Movement rules (robot)

A normal move swaps nothing; the robot just steps to an adjacent cell if that
cell is enterable. Enterability is a **tile-type rule** (CONFIRMED for every
observed pair):

- white -> white: allowed
- white -> checker : allowed
- checker -> white : allowed
- checker -> dark  : allowed
- dark -> dark     : allowed (robot moves freely within the dark zone)
- white -> dark    : **blocked** (`nothing changed`)
- dark -> white    : **blocked** (`nothing changed`)
- any -> goal (0/9): allowed (robot freely stepped onto the blue tile in L3)

So the white zone and the dark zone are **disconnected for the robot**, and the
checker is the **only bridge** between them. This was the central puzzle
constraint: to deliver the door you often have to walk a long way around
white corridors, or cross through a checker tile, to get to the right side of
the door with a matching floor type.

---

## Pushing the door

When the robot moves into the cell occupied by the door, and the cell *beyond*
the door (in the move direction) is free, the door slides one cell in that
direction and the robot takes the door's old cell. Output shows a 3-cell change:
`(beyond) base->(door-on-beyond), (door cell) ->(robot-on-door base), (robot
cell) ->(exposed base)`.

The push is only possible when the robot's floor type and the door's floor type
are **compatible**. Confirmed compatibility table (robot-floor / door-floor):

| robot base | door base (tile) | result |
|---|---|---|
| white (1)  | white (3)   | **pushes** |
| white (1)  | checker (10)| **pushes** |
| white (1)  | dark (8)    | **blocked** |
| checker(4) | checker (10)| **pushes** |
| checker(4) | white (3)   | **pushes** |
| checker(4) | dark (8)    | *untested* (predicted allowed, see below) |
| dark (2)   | dark (8)    | **pushes** |
| dark (2)   | white (3)   | **blocked** |
| dark (2)   | checker(10) | *untested* |

Separately (CONFIRMED, not part of the floor-compatibility table): the **goal
tile is a valid landing tile** for a pushed door. In every completed level the
final push sent the door onto the goal, from a white door / white-robot
configuration. Landing on the goal completes the level regardless of the other
cells.

**Leading rule (strongly supported, 7/9 cells confirmed):** a push is legal
iff the move "robot-base -> door-base" would itself be a *legal robot step* in
the direction of the push. In other words the checker bridges white/dark, and
white<->dark is forbidden both ways. The two untested cells
(dark->checker, checker->dark) are *predicted* allowed under this rule but were
never observed.

The door can be pushed onto any free base tile **or the goal**. Landing on the
goal tile completes the level.

---

## Goal / win condition

- CONFIRMED: a level completes the instant the **door lands on the goal (blue)
  tile** (`0` in L1-3, `9` in L4). All three completed levels ended with such a
  push. The robot's position at completion is irrelevant (it simply ends up on
  the door's previous cell, adjacent to the goal).
- CONFIRMED: the robot standing on the goal tile by itself does **not**
  complete the level (verified by stepping onto it in L3 and stepping off).
- GUESS: the goal's numeric code may just be a level-specific marker (0 vs 9);
  functionally it is always "the blue square the door must reach".

---

## What is still uncertain / unobserved

- Push compatibility for **(dark robot -> checker door)** and **(checker robot
  -> dark door)**. Predicted allowed (checker bridges) but never tested.
- Whether the "robot-base -> door-base = legal step" rule is the *actual* rule,
  vs. some other compatibility (the 7 confirmed cells are consistent with it).
- Exact semantics of `reset` (never used; assumed "restart current level,
  -1 action").
- Whether the goal code (0 vs 9) encodes a distinct tile type or is cosmetic.
- Whether a level can be made unsolvable by a bad sequence and recovered only
  via `reset` (I created a self-dead-end on L4; without budget left it could
  not be undone — but whether `reset` rescues a *mis-positioned* door, not a
  broken one, is untested).
- Whether there are additional hidden constraints (e.g. a par, a step limit
  per level) — none observed; the only limit is the shared 200-action budget.
- Why L4's goal is `9` while L1-3 used `0`.

---

## Outcome of this run

Completed **3 of 4 levels**. Level 4 (9x11) was not finished: with only 10
actions remaining the door needed a minimum of ~13 moves to reach the goal,
and a late push landed the door on a dark tile where only a dark-floored robot
could push it, leaving it in a dead position. Final grid status was
`levels=3/4 actions_used=200/200`, `state` no longer playable.
