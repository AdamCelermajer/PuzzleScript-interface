# AVO run notes

- Objective requires 15 level completions. Reached 4/15.
- Observed action mapping: ACTION1 moves upward/jumps; ACTION2 down; ACTION3 left; ACTION4 right; ACTION5 produced no visible effect; ACTION7 is undo.
- Tile 2 is the controllable grounded-looking avatar; tile 7 is its airborne/moving state (and also appears one cell above tile 2 on a winning transition). Tile 3 is the level objective/checkpoint; tiles 4 mark a remote target strip; tile 5 is persistent converted/painted terrain; tile 6 is its transient state; tile 1 is solid terrain.
- Levels 1-3 completed by traversing right to the tile-4 strip next to tile 3. Level 4 required jumping over tile 3, traversing the tile-4 strip, then returning from the right to tile 3.
- Level 5 requires a larger out-and-back traversal. A working outward route to the tile-4 strip was found, but it converts/falls terrain into a blocking stack and the return route to tile 3 was not found before the action budget was nearly exhausted.
- Useful exact level-3 plan from initial: R R U R U R U R R R R.
- Useful level-4 plan from x4 after preliminary straight traversal: jump over objective with U R R, traverse right, then L L L back onto objective.
- Level-5 outward manipulation used: R R R U U U L L U R U U R R D L L D U R U R U R U R R R R. This reaches the first target-strip cell but does not preserve an obvious return path.
- `probe_compact.py`, `repeat_probe.py`, and `oracle_dfs.py` were created for compact interaction and reversible search.
