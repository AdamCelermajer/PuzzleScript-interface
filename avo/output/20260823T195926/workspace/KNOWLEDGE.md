# Durable game knowledge

## Format
- current_state.json `grid`: 1=wall, 0=floor. Actions: 1=Up,2=Down,3=Left,4=Right,5=Space,7=Undo, RESET.
- 2 levels to win; 150 action budget.

## Confirmed mechanics
- Token 2 = PLAYER, one cell per direction action.
- Token 3 = BOX, pushable Sokoban-style; vacated cells become 0.
- Token 4 = IMPASSABLE to both boxes and the player (both pushes/moves into it were no-ops).
  Behaves like a wall / special obstacle (maybe a door needing a key).
- Failed moves are no-ops (changed:false) and still consume an action.
- ACTION7 = UNDO, rewinds exactly one *effective* change; no-ops are not recorded so undo
  after a no-op wastes an action.

## Derived for level 1
- Box 3 can NEVER reach 5@(1,2): to push it up col2 the player must stand at (5,2), but
  reaching (5,2) with box at (4,2) requires passing (3,1)=token 4, which is impassable.
  => The goal is NOT "push box onto 5". Most likely goal: PLAYER reaches token 5 (exit),
  with 3 (box) and 4 (obstacle) as impediments.

## Level 1 initial grid (7x6)
```
1 1 1 1 0 0
1 0 5 1 0 0
1 0 0 1 1 1
1 4 2 0 0 1
1 0 0 3 0 1
1 0 0 1 1 1
1 1 1 1 0 0
```
