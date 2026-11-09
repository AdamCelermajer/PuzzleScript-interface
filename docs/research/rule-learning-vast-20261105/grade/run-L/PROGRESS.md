# Incomplete grading: resume at seg-2

Only seg-0 and seg-1 have been read and graded in full (cp-000 through cp-008, through 48 moves). No later checkpoint has been read or graded. This is NOT the requested final report.

Both completed segment validators pass. Next: run ready.py run-L, read seg-2 start.json/handoff.md and every checkpoint in order, save labels after each. Stay inside run-L and preserve the blind restrictions. Do not infer later beliefs from this progress note.

## Findings to carry into the final report

- Before the first experimental directional action, extensive thinking measures pixels and bevels. Those early dark tiles are walls, not water; no water labels earned from those passages.
- Level 1 completion reported at move 7; level 2 at 12; level 3 at 43. Directional sliding is understood early, but manual route reasoning frequently skips walls or invents stop positions and then corrects itself.
- At cp-003 (13 moves), crate 21 is explicitly called a wall. This is I3 wrong, retained through cp-004 while alternatives are merely proposed. Move 28 push directly demonstrates movement to the wall with player following behind; I3 correct from cp-005 (29 moves). Stale notebook introduction remains but appended explicit correction wins.
- The early long stretch on level 3 investigates imaginary ACTION7 powers before recognizing undo (moves 19/20). Confirmed pass-through does not win at move 17. The crate test, undo, and planning two consecutive pushes enable the level-3 finish; not a discovery of special hopping.
- cp-007 (44 moves) treats blue 22 as another movable block. The saved solver attempts contiguous chain pushes, but stops a moving group before a separated crate and places the player behind the front crate. Thinking fixes player placement, but not the displayed saved file.
- cp-008 observes a crate consumed at the blue cell (move 47), a gold tile remaining, and continuation to the upper wall. Move 48 verifies the gold is passable. The adopted shattering/rubble description earns I6 correct for the observable rule; requiring water terminology would be too strict.
- cp-008 spends a very long time repeatedly declaring the goal or remaining crates inaccessible. Its late manual reachable-state enumeration finally notices (8,8)->(8,7)->(5,7), retracting the false impossibility claim. This is a planning/map-tracking failure after learning the fill effect, with additional untested direct-player interaction beliefs.
- cp-008 contains repeated self-summary drafting that reverts to pre-move-48 state and calls gold solidity untested. No explicit conversation-restarted header appears in the two completed segments, so no restart reset applied.

## Provisional score

At cp-004 / move 25: I1/I2/I7 correct, I3 wrong, I4/I5/I6 absent: 3/7 = 42.8571%. Later requested sample points and final table remain ungraded. At cp-008 (48 moves): I1/I2/I3/I6/I7 correct, I4 partial, I5 wrong: 5.5/7 = 78.5714%, provisional pending full-run audit.

## Audit so far and uncertainties

Reviewed all completed changes to correct/wrong against the checkpoint passages. Corrected a PowerShell encoding substitution in the cp-002 I7 quote by using an exact ASCII excerpt from the same passage; no belief label changed. Updated the propagated seg-1 start note too. Segment checker and whole-run quote checker recognize the quotes. No belief has yet been held for over 100 moves in the graded portion.

Least certain: I7 first correct at cp-002 (implicit adopted route crosses goal before its final goal landing, rather than explicit verbal distinction; move 17 is unambiguous). I4 partial rather than correct because initial contiguous chains are modeled, while new crates encountered during motion still block. I5 wrong retained at cp-008: water-as-movable assumption is increasingly questioned, but direct pushing remains in the final proposed solution and the notebook. Revisit this carefully during the requested full audit. I6 correct cp-008 despite inaccurate theme name follows rubric emphasis on observable behavior; gold-passability uncertainty in self-summary is treated as passing doubt rather than an adopted contradictory effect.
