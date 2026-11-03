# Handoff after cp-064 (1000/1000 moves, run over; levels 1-3 cleared, level 4 lost)

- Vocabulary unchanged: "character" (5/6/7), "box" (3/8/10), "target" (9), "checker" (4, grey, "decoration"), "white" (1) and "dark" (2) floor ("both walkable"), "hidden walls" (per edge), "blob", "pocket", "corridor", "bridge edges" C/D/B/X, "ping-pong ring". Files: mapdata.py (W/K), plan.py, cand.py, verify.py, solver.py, test_l4.py.
- No rule beliefs changed in cp-056..064. All beliefs carried over from start.json.
- Final notebook (cp-057, cp-059..062 versions): Sokoban push, push-only; push refused if the box's forward edge is walled or the cell beyond is off-board / not free (M3 now in the notebook too; the cp-058 interim notebook lacked it). Win = box on target, next level loads (M8). Controls ACTION1-4 plus ACTION7 undo (M1).
- Main wrong account still holds: every refused step or push is an invisible edge wall ("HIDDEN WALLS ... block char moves AND box pushes; invisible. Edge-based, not tile-based"). Colour is never named as the cause (M4, M6 partial). Grey/checker = "decoration" (M5 wrong). Box shown on white/dark/checker but the colour link is never stated (M7 partial).
- cp-056/057: probed bridge edges C, D, B (all "real walls"), then pushed the box to (2,4) as a best effort and used up the budget.
- cp-063/064 (no more game moves): writing solver.py, a BFS over (box, character) with hidden edge walls that it learns when a move is blocked. It is debugging a level-4 replica where the results come out backwards.
