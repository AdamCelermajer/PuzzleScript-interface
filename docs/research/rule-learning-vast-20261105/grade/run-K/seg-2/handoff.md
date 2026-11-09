At move 200 the player is on level 4, after resetting its failed southern route around move 193/194.
Its established core rules remain four directions, Sokoban pushing/no pulling, off-grid refusal, and white-black walking blocked with grey joining both.
M1/M3/M8 stay partial for the missing no-action-button, crate-collision, and all-crates clauses respectively.
M6 remains partial: source-versus-crate-floor relation is mostly right, but grey/black pushing is wrongly treated like walking.
It repeatedly reconsiders an unrestricted push rule, but ends with an explicitly labelled Δ2 TEST; do not score the experiment as a settled replacement.
M7 remains correct: box destination colour unrestricted, appearance depends on underlying floor (3 white,8 black,10 grey).
Target 9 proved black/h4 by cursor5 at move156; h3 solvability hypothesis withdrawn.
At move164 it catches a side-versus-above push error; repeats same error at move192, getting box to (7,2) and cursor trapped beside it.
Very lengthy move192/193 reasoning repeatedly calls incomplete, inconsistent manual search exhaustive, and misremembers old levels before self-correcting.
New level4.md at cp018 records a corner dead end; saved solver2.py already supports no pulling in the notebook from cp005.
Current route v3 reset then R R R D R U U U(test) U R U L; at move200 box heading to (2,4), next push tests white player→black crate.