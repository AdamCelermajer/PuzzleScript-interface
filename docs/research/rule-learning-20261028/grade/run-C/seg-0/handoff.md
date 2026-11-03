# Handoff after cp-008 (75 moves, level 3 of 4, levels 1-2 solved)

- Vocabulary: "box" = orange frame (crate), "goal marker" = blue frame (target), "white"/"black" floor = light/dark tiles, "door" / "checkerboard" = the grey tile, "boundary rule" = colour restriction on the player. Calls the goal cell in L3 a "white island".
- Controls: ACTION1-4 = up/down/left/right (correct). Believes ACTION7 is a "special" that "launches" the player on the checkerboard door (L1: sent one cell left); no effect elsewhere. It is about to test ACTION7 on the L3 door at (4,0). This launch belief is wrong (M1 partial).
- Sokoban push (walk into box, box moves 1 cell if destination free, else nothing) and win (box on goal marker -> instant level advance) are stated in the notebook as facts.
- Boundary rule: player cannot cross black<->white directly in either direction, only through the checkerboard door, which is passable in all directions. Briefly doubted it in the cp-006 notebook ("NOW DOUBTFUL", maybe hidden walls), then confirmed it again in L3 ((3,2)->(3,3) blocked; push from (5,2)W into the box on (4,2)B blocked).
- Pushes: it explains a refused push as the player not being allowed to enter the box's cell when that cell is the other colour. It says that if (4,2) were white, the push would be allowed (M6 graded correct at cp-007, carried from the thinking; the notebook alone shows one case).
- Boxes are not restricted by colour: "Box CAN cross black/white color boundary (L2 proven)".
- Its current belief: L3 cannot be solved by pushes alone under its rules, so "ACTION7 must matter".
