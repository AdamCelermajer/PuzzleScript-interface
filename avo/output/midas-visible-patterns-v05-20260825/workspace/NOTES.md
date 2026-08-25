# AVO run notes

- Opaque mapping from transitions: ACTION1 up/jump; ACTION2 down; ACTION3 left; ACTION4 right; ACTION5 neutral/continue; ACTION7 undo (verified sequence 730->731).
- Anonymous patterns: 2 normal player, 6 normal player up pose, 3 untouched NPC, 10 NPC contaminated/recolored by player terrain, 9 target-mode player, 11 target-mode up pose, 8 heart.
- Goal evidence: level completes when target-mode player becomes orthogonally adjacent to untouched NPC. Levels 1-3 combine touching target platform and adjacency. Level 4 required jump over the NPC without contaminating it, touch target platform, then return.
- Progress reached 4/15. Level 5: NPC at left c2, player c4, target platform c12-14, central black obstacle. The player must traverse the obstacle, touch target platform, then return. Outbound obstacle climb succeeded via repeated cycle from left: at head near wall r5c7, L,D,L,U,U,R,U,R,R,U,R; repeat/correct until r3c8, then U/R across and descend. Target-mode return is blocked because target mode does not paint missing black stair cells; outbound should pre-paint a symmetric return staircase before target conversion.
- `compact_step.py`, `summarize.py`, and search scripts preserve operational evidence summaries.

- Late discovery: ACTION7 is true undo. Level 5 outbound was solved to the target: RRRU, apply L,D,L,U,U,R,U,R,R,U,R twice to climb, then cross above. Normal-mode route can paint r4c10 using U,R,R,D before target contact, but this cell alone blocks rather than enables the target-mode return; a lower/right staircase must be prepared before conversion.

- Environment budget exhausted at 1000 steps, progress 4/15. Final state remained target-mode on the right side of level 5 after a return attempt; evaluator success remained false.
