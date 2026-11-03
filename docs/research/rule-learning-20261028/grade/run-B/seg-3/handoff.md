# Handoff after cp-016 (181 moves, level 5 unsolved; levels 1-4 cleared, L4 at 144 actions)

- Its own words: "creature" (player), "water" (ice floor, tile 6), "plant" (goal), "boxes" (crates), "doors" (water tiles 22-26, drawn blue; "gold"/"ring" 27 after a box is absorbed). L5 has four doors in a diamond around the plant at (5,6), four boxes, and a wall tile 31.
- I1/I2 correct: ACTION1-4 slide up/down/left/right until the next tile is an obstacle. ACTION7 = undo.
- I3 correct: the pushed box slides to the end of its path and the creature stops one tile behind it. A box that cannot move means the creature stops next to it.
- I4 wrong (thinking only): it still says a box pushed into another box cannot move ("box (5,3) -> (5,4) = box 2 -> box 0 movement"). Its whole "all L5 boxes are permanently stuck" argument rests on this, plus "in a push only one box moves at a time".
- I5 partial: the L5 blue doors block the creature in all 5 rotor states (door (4,6) from above, (5,7) from the right, tested many times), and it calls them "100% impassable". But it still believes the L4 blue door was vertically passable for the creature.
- I6 correct (thinking; notebook still partial): a box pushed into a blue door is absorbed and disappears, the door turns gold, and the pushing creature carries on through. New at cp-015: "gold door = horizontal passage open". Its L5 plan is to absorb a box so a door becomes passable.
- I7 correct: it stops on the plant to win (L4 won by A3 from the door tile onto (3,1)). For L5 it wonders whether passing over the plant also counts, but has not adopted that.
- Other beliefs (not graded): the door number is a shared rotor that advances by (tiles moved + 1) mod 5 each move. Tile 31 is a wall. The left region of L5 is one-way: you can leave it through (3,11)->(1,11) but never get back. Next: press A3 again and again from (5,8) to test whether a hidden counter opens door (5,7).
