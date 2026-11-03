# Handoff after cp-037 (752 moves, level 4 of 4 in progress, levels 1-3 cleared)

- Vocabulary unchanged: "character" (5/6/7 = on dark/checker/white), "box" (3/8/10 = on white/dark/checker), "target" (0 blue, 9 dark blue in level 4), "checker" (4, grey), "white" (1) and "dark" (2) floor, "hidden walls" between cells, "cluster", "blob", "row-7 chain", "dead cells", "corner edges".
- Notebook rewritten at cp-035 (plan v2, wall list, failures); unchanged at cp-036/037. Same rule content as the cp-033 version: controls, Sokoban push, win = box onto target 0/9, "4 = checker (decoration, no effect)", "HIDDEN WALLS between some adjacent cells: block char moves AND box pushes".
- No rule beliefs changed in cp-035..037; all labels carried over from start.json.
- Main wrong account still holds: every refused step or push is a hidden wall between two cells (about 43 walls listed). Colour is never given as the cause (M4 partial, M6 partial). Grey/checker still "decorative" (M5 wrong).
- Box is pushed onto/through dark cells in its plans without any link to who can push it next (M7 partial).
- At cp-037 it wrote a BFS solver over its wall map. With all unknown edges open it found no path, so it decided its wall list must hold a mis-recorded "false wall". It is about to re-test single walls in the game (candidates (2,4)-(3,4), (5,1)-(5,2), (6,1)-(6,2), (4,0)-(5,0)). It briefly asked "maybe the character can pull the box?", "maybe ACTION5/6 become available?" and "one-way movement restriction?" but adopted none of these.
- New walls it tested: (1,3)-(1,4) and (4,0)-(3,0).
