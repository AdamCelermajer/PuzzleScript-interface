# Handoff after cp-024 (326 moves, game WON 6/6, final notebook written at cp-021..023, then solver.py drafted)

The notebook was rewritten at cp-020 and refined at cp-021..023. It now holds the full model, so most labels have source "both". No belief changed in this segment.
- Vocabulary: tile codes 0 brick, 1 grass, 2 player, 3 bright ring (red crate), 4 socket (target), 5/9 dashed ring on grass/socket, 6/7 dark ring on grass/socket, 8 cage (ring on socket). Ring/cage tiles are "portals"; the landing pair is the "bar" (centre C, ends e1/e2).
- K3 (correct): when you enter ring R moving in direction D you freeze at R; C = R+2D (any in-grid tile); the ends are C plus or minus rot90cw(D).
- K4 (partial): an end on brick or holding a ring/cage is "suppressed"; the dark ring starts at e1, or at e2 if e1 is suppressed. Still no "move refused when no landing cell is free". Its wrong part: in its solver a bar is invalid if C or either end is off the grid, and its shadow lets you enter even when both ends are suppressed.
- K5/K6 (correct): while frozen, an arrow toward an end swaps dark and dashed. ACTION5 commits: a cage on a socket, a bright ring on grass. The player is released at R.
- K7 (partial): "a level completes exactly when no bright rings remain" (every ring caged). It is stated from the rings' side, and it notes that every level had as many sockets as rings.
- K2 (partial): brick is impassable. It has never seen orange crates.
- Wrong side-belief, still held: ACTION7 undoes walks, flips and commits but not a portal entry.
