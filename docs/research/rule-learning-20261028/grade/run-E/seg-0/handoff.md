# Handoff after cp-029 (629 moves, level 4 of 4 in progress, levels 1-3 cleared)

- Vocabulary: "character" (IDs 5/6/7 = character on dark/checker/white), "box" (orange hollow square; 3 = box on white, 8 = on dark, 10 = on checker), "blue target" (0; in level 4 the target is tile 9, "dark blue" variant), "checker" (4, grey), "white" (1) and "dark" (2) floor, "hidden walls" between cells.
- Controls: ACTION1-4 = up/down/left/right, ACTION7 = undo the last do; ACTION5/6 "not available". Graded M1 correct.
- Sokoban: walking into the box pushes it one cell; push refused off-grid or into a wall/box (M2, M3 correct). Goal: push the box onto the blue target, the level then ends (M8 correct in thinking; the notebook still says only "hypothesis").
- Main wrong account: it thinks refused steps come from invisible per-edge "hidden walls" placed by the designer. It noticed early that they sit on white-dark boundaries, but then dropped colour as the cause ("walls exist per edge", "not strictly limited to white-dark") and now maps walls edge by edge. M4 is partial for that reason; nothing about grey/checker as a bridge (M5 absent).
- It also blames refused pushes on walls (sometimes box-only or one-way walls). M6 partial. It briefly held "box can't cross dark->blue" (M7 wrong at cp-014), then dropped it at cp-021 after the dark->blue push worked; M7 now absent.
- Notebook was last rewritten at cp-005 (before level 1 was cleared). It lists specific hidden walls for level 1 and the Sokoban box rules.
- At cp-029 it is mapping a large level-4 maze for an entrance to the "cluster" near the box at (4,3). It has just found (0,6)->(1,6) open.
