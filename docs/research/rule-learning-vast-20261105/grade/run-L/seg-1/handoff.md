Through cp-008 (48 moves), L4, levels 3/6; no conversation restart marker so far.
I1/I2/I3 remain correct; ordinary sliding and single-crate push established and retained in state.md.
I4 partial: adopts contiguous chain movement, but solver stops before a non-group crate rather than picking it up mid-slide.
I5 wrong: blue 22/24/25 at (3,4) was modeled as movable, with direct-player push still used in the final proposed solution; alternatives remain untested.
I6 correct in thinking at move 48: crate consumed at blue tile, blue changes to passable gold, player continues across. Theme calls it shattering/rubble, not water/filling, but observable rule matches.
I6 notebook remains wrong: solver.py treats blue as a movable block in chains.
I7 correct in both: solver.py tests goal only on final resting states, plus explicit thinking confirmation.
cp-007 solver has errors: static original movable cells stay closed; player placed behind front not rear crate; stops group before new crate.
Thinking corrects front/rear logic, but these corrections are not in the displayed saved solver.py.
cp-008 has huge repeated speculative plans and self-summary attempts; one summary regresses to pre-move-48 position and calls gold passability untested, despite test earlier in this checkpoint.
Late cp-008 finally reconstructs a route via (8,8)->(8,7)->(5,7), correcting its repeated false claim that remaining crates cannot be reached.
Next unread checkpoint is in seg-2; run ready.py run-L before proceeding.
