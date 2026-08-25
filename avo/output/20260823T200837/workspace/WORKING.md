# Level 1 working state (after 3 actions)

Grid now:
row0: 1 1 1 1 0 0
row1: 1 0 5 1 0 0
row2: 1 3 0 1 1 1
row3: 1 2 0 0 0 1
row4: 1 0 0 3 0 1
row5: 1 0 0 1 1 1
row6: 1 1 1 1 0 0

Player (3,1). Boxes (2,1) and (4,3). Goal 5 @ (1,2).

Plan (verified by simulator): R R R D L U L L D D R U U U
-> ends with box on (1,2). Expect WIN / level advance.
If not a win, the goal may require BOTH boxes on goals -> then need a second 5 somewhere;
fallback: examine new grid.
