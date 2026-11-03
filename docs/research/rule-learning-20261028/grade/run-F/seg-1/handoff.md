# Handoff after cp-009 (50 moves, level 4 in progress, 3/6 cleared)

- Vocabulary: "ice" = floor; "plant" = goal; "orange crate" = crate; "holes"/"notches"/"dark" cells = blockers; "the blue"/"blue glyph" at L4 (3,4) = a blue, digit-shaped object whose ID kept changing (22-26) every turn. By its behaviour it is very likely water. Coordinates are local (r,c).
- Controls (correct): ACTION1-4 = slide up/down/left/right. It thinks ACTION7 = "reverse slide" (not graded).
- Sliding (correct): one action slides until a wall, dark blocker, crate or (blocking) blue. The plant does not stop a slide.
- Win (correct): the level completes only when a slide ends on the plant.
- Crate push (correct, thinking only): the crate slides until it hits something and the player stops right behind it.
- Chains (WRONG): it assumes a crate pushed into an adjacent crate does not move ("can't push a crate with a crate", "stops immediately (adjacent crate). No move"). It briefly called chain pushes "untested", then went back to assuming they fail.
- The blue (water): it believes the blue is a gate that cycles between states, blocking in some (22, 25) and passable in others (24, 27). At move 46 a crate pushed up into it vanished ("absorbed"), the blue became ID 27, and the player slid through. From then on 27 stayed passable. It credits the passability to the blue's "state", not to the crate filling it. Graded partial for I5 (blocks, but "passable in some states") and partial for I6 (crate disappears and the player passes, wrong cause).
- It also said "crates stop before holes" (dark rimmed squares). That was not counted against I6, since the holes are probably not water.
- Current plan: it thinks the L4 plant is unreachable and is now "feeding" the remaining two crates to the blue as its goal guess. The notebook has not been rewritten since cp-006.
