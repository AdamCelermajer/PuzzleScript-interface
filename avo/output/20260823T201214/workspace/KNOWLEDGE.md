# Durable game knowledge

## Format
- grid = row-major list of rows, small ints. Actions: 1=Up,2=Down,3=Left,4=Right,5=Space,7=Undo,RESET.
- Need 2 levels. Budget 150.

## CONFIRMED mechanics
- **2 = player**, moves 1 cell/action, leaves underlying tile behind.
- **1 = wall**, blocks (no-op).
- **3 and 4 are PUSHABLE BOXES (Sokoban)**. Confirmed T000003: player at (4,1) pressed Up,
  box at (3,1) moved to (2,1), player to (3,1).
- **IMPORTANT: token 4 turned into token 3 when pushed.** Before: 4 @ (3,1). After: 3 @ (2,1).
  So 4 may = "box not yet moved" vs 3 = "box moved", OR 4 = box-on-something. Treat 3 and 4
  as the same object type for movement purposes.
- **5 = goal/target tile** (floor marker). Player can stand on it; it reappears when leaving.
- Push blocked if destination is wall or another box (no-op). Earlier L into 4 at (3,1)
  was a no-op because (3,0) is wall -> consistent.

## Goal hypothesis
- Push a box onto the 5 tile. (Only one 5 in L1, two boxes -> probably any/one box suffices.)

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

## Solution path for L1 from initial state (17 moves)
D L U R R R D L U L L D D R U U U
(= ACTION2 3 1 4 4 4 2 3 1 3 3 2 2 4 1 1 1)
First 3 already executed (D L U). Remaining 14: R R R D L U L L D D R U U U.
