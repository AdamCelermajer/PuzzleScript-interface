# Durable game knowledge

## Format
- grid = row-major list of rows, small ints. Actions: 1=Up,2=Down,3=Left,4=Right,5=Space,7=Undo,RESET.
- Need 2 levels. Budget 150.

## Confirmed mechanics
- Token **2 = player**; moves 1 cell per action; leaves the underlying tile behind.
- **Player can stand ON token 5** and 5 REAPPEARS when player leaves => 5 is a floor
  marker/target (NOT a collectible). Nothing happened when standing on it.
- 1 = wall; moving into wall = no-op (empty diff).
- Token 4 @ (3,1): moving left into it from (3,2) was a NO-OP. Either 4 is solid, or 4 is
  a pushable box whose push was blocked by wall at (3,0). Unresolved.
- Token 3 @ (4,3): not yet touched.

## Level 1 initial grid (7x6)
```
row0: 1 1 1 1 0 0
row1: 1 0 5 1 0 0
row2: 1 0 0 1 1 1
row3: 1 4 2 0 0 1
row4: 1 0 0 3 0 1
row5: 1 0 0 1 1 1
row6: 1 1 1 1 0 0
```
Open floor cells: (1,1),(1,2),(2,1),(2,2),(3,1),(3,2),(3,3),(3,4),(4,1),(4,2),(4,3),(4,4),(5,1),(5,2).

## Geometry notes for L1 (if 3 and 4 are Sokoban boxes)
- Box 4 in col1: can only be pushed vertically (walls at col0; (3,0) wall blocks left push;
  can't stand at (3,0) to push right). Range (1,1)..(5,1).
- Box 3 in row4: can only be pushed horizontally ((5,3) is wall so no up-push possible;
  (3,3) open so down-push would hit wall (5,3) => fails). Range (4,1)..(4,4).
- Target 5 at (1,2) cannot be reached by either box under those constraints => so the
  Sokoban-push-onto-5 hypothesis is probably WRONG, or pushing works differently.
