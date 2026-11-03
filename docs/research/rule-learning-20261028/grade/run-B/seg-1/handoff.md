# Handoff after cp-008 (80 moves, level 4 just reset)

- Its own words: "creature" (player, tile 9), "water" (floor/ice, tile 6), "plant" (goal, tile 5), "boxes" (crates, tile 21), dark "blocks" and frame tiles = walls. On level 4 the water cell at (3,4) is a "door"/"head" with rotating states 22-26; it never calls it water.
- I1/I2 correct: ACTION1-4 = slide up/down/left/right until the next tile is an obstacle. ACTION7 is now believed to be "undo" (reverses the previous slide); whether undo restores pushed boxes is untested. Not graded.
- I3 correct: the box slides to the end of the path and the creature stops right behind the box's final position; an immovable box means no move.
- I7 correct: landing on the plant clears the level; passing over it does not.
- I5 partial: the door head blocks the creature horizontally in all states 22-26 (it stops in front). Wrongly, it believes vertical passage through the door column is "always allowed", and that the door has a "body" at (4,4)-(6,4) that blocks the row-6 crossing (its "beam" idea).
- I6 partial: pushing a box into the door head "absorbs" it (box disappears, head becomes state 27, a "gold ring"), and the creature followed through vertically. It thinks only the door absorbs boxes, and horizontal passage over state 27 is "untested".
- I4 wrong (new at cp-008): it reasons that a box pushed into another box is blocked ("box 2 blocks -> box 3 can't move", "frozen pair"). At cp-006 it had left the chain question open.
- Other odd beliefs: the row-3 zone is a "one-way trap"; it doubts the plant is the level-4 goal; the door state also changes on nearby slides. Next plan: test undo+push "banking", then feed box 2 and box 1 into the head.
