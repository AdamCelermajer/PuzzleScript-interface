# Handoff after cp-042 (804 moves, level 4 of 4 in progress, levels 1-3 cleared)

- Vocabulary unchanged: "character" (5/6/7 = on dark/checker/white), "box" (3/8/10 = on white/dark/checker), "target" (0 blue, 9 dark blue), "checker" (4, grey), "white" (1) and "dark" (2) floor, "hidden walls" (edges), "pocket" {(5,2),(6,2),(7,2)}, "central cluster", "blob", "row-8 sweep", "false wall", "corner edges".
- Notebook rewritten at cp-038 and cp-041 with the same rule content: Sokoban push, win = box onto target 0/9, "4 = checker (decoration)", "1 = white floor, 2 = dark floor (both walkable)", "HIDDEN WALLS between some adjacent cells: block char moves AND box pushes". Controls plus ACTION7 undo.
- No rule beliefs changed in cp-038..042. All labels are carried over from start.json.
- Main wrong account still holds: every refused step or push is an invisible edge wall. At cp-038 it briefly guessed "1 = floor, 2 = wall" from the grid, then dropped it ("both 1s and 2s are walkable, walls are invisible edges"). Colour is never named as the cause (M4 partial, M6 partial). Grey/checker is still "decoration" (M5 wrong).
- New evidence it explained as walls: a push of the box from dark (2,4) by a character on white (3,4) was refused, and it logged "(1,4)-(2,4) is a WALL (was wrongly in K)". Its tests of the column-1, row-8 and pocket edges (white-dark boundaries) all came back "real wall".
- It now thinks its wall map holds mis-recorded "false walls". It found one, (2,4)-(3,4): the box on white was pushed onto dark (M7 still partial, with no link to who can push next).
- At cp-042 it is testing (0,3)-(1,3) next, then (3,2)-(3,3). The box is at (4,3) and the character at (6,2).
