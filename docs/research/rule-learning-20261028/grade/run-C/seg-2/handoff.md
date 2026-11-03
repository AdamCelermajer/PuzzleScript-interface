# Handoff after cp-030 (225 moves, level 4 of 4, levels 1-3 solved)

- Vocabulary: "box" = crate (orange frame), "goal" = blue target, "white"/"black" floor (W/B), "door" / "checkerboard" = grey tile, "wall" / "B-W edge" = a refused step between a white and a black cell. In L4: "left cluster" / "right cluster" = white regions, "upper band" / "central black" / "lower-left chain" = black regions. Texture ids are anonymous per level.
- Controls: ACTION1-4 = up/down/left/right. The notebook still says ACTION7 on the door "launches the player 1 cell back the way they came" (wrong; M1 partial). The cp-030 context summary no longer mentions ACTION7.
- Push (box moves 1 if destination free, else nothing) and win (box on goal -> next level; L4 win = game win) are notebook facts. "Boxes cross B-W freely" (M7 correct).
- Colour rule (M4 correct since cp-026): notebook says "Assume all B-W edges walled except door" (L4: 13/13 tested walls, L3: all tested walls). The "Movement rules" section still frames them as "hidden per-level WALLS" on specific edges. At cp-029 it is hoping that an untested edge, (4,0)W-(3,0)B, is open, and is about to probe it.
- Door: "freely passable in all directions" (M5 correct). This includes door-to-black pushes, which the true rule refuses for a player on grey. That is a minor gap.
- Pushes (M6 correct since cp-026): "Pushes crossing boundary walls are blocked". The box at (3,7)B "can only be pushed by a pusher moving B-B". "Keep the pusher on a same-color floor and let the box cross boundaries."
- Current L4 state: box (3,5)W. The player is stepping from (4,1)W to (4,0)W, then it will probe up into (3,0)B. Its long winning route depends on that edge being open.
