# Handoff after cp-006 (37 moves, level 3 about to be cleared)

- Vocabulary: "ice" = floor (ID 6); "plant" (green, ID 5) = goal; "player"/face (ID 9); "holes"/"rimmed dark squares"/"notches"/"gap"/"pit" (dark cells, IDs 7, 8, 18, 3, ...) = impassable blockers; "orange crate"/"wooden crate" (ID 21, yellow border, brown inside); field coords are local (r,c) per level.
- Controls: ACTION1/2/3/4 = slide up/down/left/right (all confirmed). It believes ACTION7 = "reverse slide" in the direction opposite the last slide, and calls it redundant. (Wrong reading: its observations fit an undo, but undo is not one of the graded rules.)
- Sliding: each action is one full slide until the next cell is a wall, a dark blocker or a crate. The plant does not stop a slide.
- Dark cells: the player cannot enter them and stops in front of them (rated correct for I5). It never says any dark cell is water.
- Win: the level completes only when a slide ENDS on the plant; sliding through the plant does not count (notebook "WIN RULE REFINED").
- Crate (new at cp-006, thinking only): slide-push is confirmed. The crate slides until it hits a blocker, and the player slides along and stops right behind it. The notebook was not rewritten yet, so it still lists only blockers.
- No belief yet about crate chains (I4) or about a crate filling water (I6). It has only seen a crate stop against a dark notch.
