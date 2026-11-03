# Handoff after cp-032 (226 moves, level 4 of 4, levels 1-3 solved)

- Vocabulary: "box" = crate, "goal" = blue target (0,3)G, "white"/"black" floor (W/B), "door" = grey tile (4,2)D, "wall" / "B-W edge" = a refused player step between white and black. Components: "upper black" (rows 0-1 etc.), "central black" (reached via the door), "lower-left black".
- Controls: ACTION1-4 = up/down/left/right (restated in thinking). The unchanged notebook still claims ACTION7 on the door "launches the player" (wrong; M1 partial).
- Push / blocked push / win (box on goal -> level advance) unchanged and correct.
- Key new statement: "walls block the player but not the box"; "A push is legal iff the pusher's step is legal ... the box ignores walls" (M6, M7 correct).
- Colour rule now weakened (M4 partial): 14/14 tested B-W edges are walls, but it concluded "Since the game is presumably winnable, at least some B-W edges must be open" and plans a route that needs untested edges (4,7)W-(3,7)B, (2,5)-(2,6), (2,4)-(2,5) to be open for the player. The unchanged notebook still says "assume all B-W edges walled except door".
- Door still "freely passable in all directions" (M5 correct), with passing doubt about whether door->(5,2)B is open.
- Current plan: push box (3,5)->(3,6)->(3,7), detour 24 moves to (4,7)W, push up (probing (4,7)-(3,7)), then push it left along row 2 and up column 3 to the goal. It is about to rewrite the notebook with this plan.
