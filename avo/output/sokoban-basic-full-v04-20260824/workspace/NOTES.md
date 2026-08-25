# AVO run notes

## Observed action mapping

- `ACTION1`: up
- `ACTION2`: down
- `ACTION3`: left
- `ACTION4`: right
- `ACTION7`: undo (recorded no-op inputs can also require undoing)
- `ACTION5`: no visible effect in tested positions

## Level 1 observations

- Numeric tile 1 is wall, 0 is floor, 2 is the controlled player-like object.
- Tile 3 is pushable by walking into it when the next cell is open.
- Tile semantics confirmed from observed transitions: `3` is a movable box, `5` is an empty goal, and `4` is a box already on a goal. A goal is temporarily hidden by the avatar and reappears when it leaves.
- A box cannot be pushed into tile `4` because that cell already contains another box.
- Initial last grid:
  `111100 / 105100 / 100111 / 142001 / 100301 / 100111 / 111100`.
- Win condition: every box must occupy a goal. Completing level 1 loaded a second grid; putting all three level-2 boxes on goals produced authoritative `status: WIN`, `terminal: true`, and `success: true`.

## Solver and result

- Built `sokoban_solver.py`, a local BFS over `(player, box_positions)` using only the observed wall map and persistent goals.
- From the recovered level-1 state, the verified BFS plan completed level 1 in 34 moves.
- A second 16-move BFS plan completed level 2.
- Final evaluator result after 84 total environment actions: terminal success (`score.success = 1`).
