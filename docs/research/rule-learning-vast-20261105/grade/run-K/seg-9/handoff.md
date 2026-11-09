At cp-053 (602 moves), four directional actions are known, but the unused action button is unestablished (M1 partial).
M2 returned to correct at cp-044: same-height ACTION7 test @432 refuted conditional dragging; level4k explicitly says box only PUSHED.
M3 knows in-bounds pushes, with no multi-crate collision knowledge; M8 states box-on-target for the single crate (both partial).
M4/M5 are correct: h2=white, h3=grey, h4=black and walking |dh|<=1. A possible climb was a test, not an adopted new rule.
M6 remains partial: pushing is still modelled as the same |dh|<=1 cursor step, missing the grey/black exception.
M7 is correct: the box may enter any floor, then its floor affects later pushing; display 3/10/8 tracks white/grey/black.
At 441 the repeated climb test fails; the player finds solver4's wrong (3,4) floor, corrects it inline and obtains SOL.md's 158-move route.
The corrected route advances steadily from reset 442/443 to the last push at 602; no new rule discovery is needed.
Self-summaries around 497 falsely revert progress to step 3/15, causing an extra A1; at 498 the grid restores step 54.
All current sources are both; latest notes override old sliding-puzzle/drag files, which remain present.
