# Durable game knowledge

## Confirmed

- Tile `2` is the controllable actor; directional actions move it one cell on traversable terrain.
- Tile `0` is traversable floor.
- Tile `1` is impassable to boxes and is strongly supported as wall terrain.
- Tile `3` is a pushable box. Directional movement pushes it one cell when the cell beyond is free; pushing fails when the destination is occupied by tile `1` or tile `4`.
- Tile `5` is persistent traversable goal terrain: the actor temporarily hides it, and it restores when the actor leaves. Merely walking over it does not win.
- Tile `4` is a box on a goal. Pushing it off changed it to tile `3`; its former cell became actor `2` while covering the persistent goal.
- Pushing a box back onto a goal changes it from tile `3` to tile `4` (observed at `(3,1)`).
- Failed hypothesis: tile `4` is not a free goal that accepts tile `3`.

## Solver

- `helpers/sokoban_solver.py` implements BFS using confirmed tile semantics.
- From the initial level-1 state, this model finds a 33-move solution: `DLURRRDLULLDDRULURUULDRDDRRULDLUU`.
- Level 1 was completed exactly by that solution; victory occurs when every box occupies a goal.
