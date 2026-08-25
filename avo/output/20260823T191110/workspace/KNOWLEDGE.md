# Durable game knowledge

## Confirmed mechanics

- Harness actions: ACTION1/2/3/4 = Up/Down/Left/Right; ACTION5 = Space/Action;
  ACTION7 = Undo; RESET restarts the current level.
- Grid codes: `0` traversable floor, `1` wall, `2` avatar, `3` movable box,
  `5` unoccupied goal, `4` box on goal.
- Directional movement is one orthogonal cell. Entering a box pushes it one cell
  only when the cell beyond is free; otherwise movement is blocked.
- Goal state persists under occupants: the grid temporarily shows `2` when the
  avatar stands on a `5`, and restores `5` after it leaves.
- Pushing a box off a goal changes `4 -> 3` and reveals the goal after the avatar
  leaves (T000021-T000022). Pushing a box onto a goal changes `5 -> 4` (T000040).
- ACTION5 had no observable effect adjacent to a box-on-goal (T000017).

## Goal

- Confirmed by T000051: a level completes immediately when every box is on a
  goal. The next level loads in the same transition.

## Recorded failures

- A box cannot be pushed into a box-on-goal (`3` into `4`); T000008 was blocked.
- Moving the lower box left to `(4,1)` before freeing the occupied goal deadlocks
  it; RESET was required.
