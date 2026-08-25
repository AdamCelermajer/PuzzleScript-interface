# AVO run notes

Mapped actions from observed transitions:
- ACTION1: up/jump
- ACTION2: down/descend
- ACTION3: left
- ACTION4: right
- ACTION5: no visible contextual action in tested states
- ACTION7: undo (confirmed by restoring prior player/object state)

Mechanics inferred from evidence:
- Player leaves/propagates paint onto adjacent supporting/wall cells (1 -> active 6 -> settled 5).
- Unique object 3 must remain unpainted until player has contacted the color/clean region 4; after visiting 4, return/contact 3 produces celebration object 7 and increments levels_completed.
- Jump state uses object 8. A horizontal move during a jump can create a cling/reset only in some wall-adjacent geometries.
- Framework reset preserves cumulative level progress while restoring the current level.

Completed levels 1-3 by navigating to object 3 / the region next to it. Level 4 required preserving embedded object 3 by jumping over its column, reaching region 4, then returning; sequence from c5 was U,U,R,R,R,R to region then L,L,L, which raised progress to 4.

Blocked at level 5. Layout: 9x17, player (6,4), object3 (6,2), region4 row7 cols12-14. Solid barrier around column8, with row4 cols6-10 and upper blocks. Direct left approach paints object3; direct right route is blocked. Extensive controlled and randomized exploration did not find a barrier-crossing sequence. Boundary route after sacrificing object reaches at most row4 and cannot preserve object. Remaining budget was insufficient for 11 further levels.
