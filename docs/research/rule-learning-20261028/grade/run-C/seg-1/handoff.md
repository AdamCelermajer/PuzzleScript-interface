# Handoff after cp-016 (109 moves, level 3 of 4, levels 1-2 solved)

- Vocabulary: "box" = orange frame (crate; texture 3 on white, 8 on black), "goal" / "goal marker" = blue frame (target), "white"/"black" floor, "door" / "checkerboard" = the grey tile, "edge" / "wall" = a refused step between two cells, "goal island" = the L3 goal cell (3,2), "pocket" = white cells {(1,1),(1,2),(2,1)}.
- Controls: ACTION1-4 = up/down/left/right. It also believes ACTION7 on the door "bounces" the player one cell back the way it came, and possibly works as a general "backstep" (wrong; M1 partial).
- Push (walk into box, box moves 1 if destination free, else nothing) and win (box on goal -> instant level advance) are notebook facts. "Box can cross black/white boundary freely" (M7 correct).
- Colour rule (M4 partial since cp-010): it now says refused steps are "hidden per-level WALLS" on specific edges along the colour boundary, "not a universal rule". It keeps probing white/black edges in L3 expecting some to be open. All probes were refused. The notebook still also says "Player enters/leaves black ONLY via door".
- Door: "freely passable in all directions" (M5 correct).
- Pushes (M6 partial since cp-010): it explains refused pushes (T71 from (5,2) up, T106 from (3,4) left) as walled edges, not as the player's floor against the box's floor. At cp-016, after a context summary, it forgot that the T71 push failed. It now asks whether "walled boundary edges block PUSHES" (open question). Its plan F2 hopes that a push from (5,2)W into the box on (4,2)B will win.
- Current L3 state: box (3,3)B, player (1,4)W. Next move is to push the box down from (2,3) to test edge E1.
