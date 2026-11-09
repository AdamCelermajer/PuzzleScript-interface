# Handoff after cp-028 (244 moves)
- Read cp-024–028 fully and saved each checkpoint; cp-027 restored I7 correct, cp-028 wrongly rejected it again.
- Pass-count and consecutive-direction tests through 211 fail; undo after push at 225 restores the full state.
- At 228, intending to stop before B, the player instead pushes B from (5,4) to (1,4); this separates the pair.
- It realizes A alone fills the left water while the right water stops it on the goal. It adopts stop-on-goal again, then wins level 5 at 243.
- The long preceding proofs wrongly treated paired crates as inseparable and movable crates as stops. They did not establish an engine bug.
- cp-028 is explicit restart #2; it restates blocking water, per-cell filling, pushing, and initially stop-on-goal, so these do not reset to notebook errors.
- Final level starts P(9,10), goal(9,5), crates(3,9),(3,10),(8,4), water(3,6),(5,5). At 244 it again declares stop-on-goal impossible and adopts an unspecified alternative win.
- Thinking mixes correct chain pushes with an explicit separated-crate stopping model; I4 remains partial. Notebook stays I1/2/3/6 correct, I4 partial, I5/7 wrong.
- Latest combined: I1/2/3/5/6 correct, I4 partial, I7 wrong. Next planned route pushes row-3 pair left to fill (3,6).
