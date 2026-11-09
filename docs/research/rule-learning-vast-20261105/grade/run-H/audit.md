# Run H skeptical audit

Completed after the full sequential reading and initial grading. This records the final audit decisions, including a second review of the proposed K3 upgrade. Intervals below end at the next change, or move800; they are elapsed move spans, not exact costs attributed to a belief.

## Every transition to correct or wrong

| Checkpoint / move | Rule / new label | Exact label evidence | Audit decision |
|---|---|---|---|
| 004 / 40 | K6: correct | N: ACTION5 = clear enemies (5/6) -> goal 3 spawns at (4,6) [position of 6 at that moment] | Correct behavioral confirmation: current6 becomes red and markers clear; files also say normal movement returns. Enemy vocabulary does not negate the effect. |
| 006 / 75 | K1: correct | T: Force a swap so 6 goes to (2,6) | Deliberate direction-to-swap followed by ACTION5 is operational confirmation of a choice. Basic direction mapping was already known. |
| 007 / 100 | K3: correct | T: 2 tiles behind (below, since I was moving down), 1 tile to the left and right. | Vertical observations at91/100 complete the horizontal two-forward/one-side rule; both marker positions can be made6. Credit at this checkpoint. |
| 012 / 225 | K7: wrong | T: The most natural win condition: enter the goal while carrying the item. Let's go with that. | An explicit adopted carry-entry objective, not merely another proposed test. No substantial coverage component. |
| 018 / 330 | K7: wrong | T: the level's purpose = enter a goal while an enemy is present. | Explicit leading objective adopted in the thinking at329; repeated as top idea in the later notebook. No substantial coverage component. |
| 029 / 475 | K7: correct | T: rule = "6 on plain item + 0 other plain items + ACTION5," | Conserved plain/held targets plus zero other plains expresses all targets covered. It is the leading conclusion at469, not an equal alternatives list. |

The departure from K3 correct at008 was also rechecked: the adopted westward-entry plan into (2,6) predicts (3,4)/(5,4), instead of the true pair. Its exact note is `T: Then: enemies 6@(3,4), 5@(5,4)`. Repeated later one-row shifts and inconsistent axes support partial; I did not leave the proposed correct label in force through275. The K1 downgrade at015 is the explicit restart, not ordinary silence.

## Every combined label lasting more than100 moves

| Rule | Label | Interval | Rechecked anchors and decision |
|---|---|---|---|
| K1 | correct | 75 to 299 (224 moves) | cp006 deliberate swap-and-confirm; later cp012-014 still attempt a swap, read6, then ACTION5. Preserve until marked restart299. |
| K1 | partial | 299 to 800 (501 moves) | cp015 retains directions and clear-at6 only; cp019/021 formalize fixed marker effects; cp031/046 still lack general direction-based choice. |
| K2 | partial | 13 to 800 (787 moves) | cp001 explicitly excludes walls; cp004 calls walls impassable; later route plans exclude wall approaches. Final files do the same. No ordinary orange crate appears; dark item is a target. |
| K3 | partial | 125 to 800 (675 moves) | cp008 adopted wrong pair; cp010-014 mix correct formulas with repeatedly wrong route offsets. After299 the notebook has a one-case transition; cp019/021/031/046 have fixed6 destinations and incomplete other-side geometry. Substantial correct entry/jump effects remain. |
| K4 | partial | 25 to 800 (775 moves) | cp002 refusal observed; cp004 incorrect item-adjacency cause; cp010 wall-invalid candidates; cp019/021 false opening rule; cp031/046 wall/crate validity but missing player occupancy and wrong both-invalid entry behavior. Never complete. |
| K5 | partial | 25 to 800 (775 moves) | cp002 genuine swap observed with wrong successful-movement explanation; cp003 recount confirms immobility; cp006 directional swaps; cp013 lock; cp019/021 rows/pullback; cp029 quadrant; cp030/031/046 global immobility with false row cause. Correct effects survive the cause changes. |
| K6 | correct | 40 to 800 (760 moves) | cp004 current6->red and movement returns; cp005/006 different red locations; cp015 retained files; cp019/021/031/046 same action effect. Other wrong entry/selection explanations do not replace this effect. |
| K7 | absent | 1 to 225 (224 moves) | cp000 possibilities; cp004 UNKNOWN; cp006-011 carry-entry and alternatives presented as tests rather than settled objective. First explicit adopted carry-entry rule at225. |
| K7 | partial | 358 to 475 (117 moves) | cp021 leading red-on-target plan; cp023 first win; cp025 second win but consumption explanation; cp027/028 competing closest/sole-item accounts. Conservation plus settled all-covered rule not sustained until cp029. |
| K7 | correct | 475 to 800 (325 moves) | cp029 leading no-other-plain rule after conservation; cp031 notebook best fit; cp032-045 persist while parking; cp046 final file retains best-fit coverage with listed uncertainty. No newer adopted contradiction. |

## Files-alone labels lasting more than100 moves

| Rule | Notebook label | Interval | Audit basis |
|---|---|---|---|
| K1 | partial | 13 to 800 (787 moves) | Direction mapping and ACTION5 effect remain in files; no complete directional choice procedure. |
| K2 | partial | 40 to 800 (760 moves) | Wall knowledge survives; ordinary orange-crate pushing is not recorded. |
| K3 | partial | 13 to 800 (787 moves) | One-case entry then side-knight formulas; fixed6/other-slot confusion and no complete either-choice rule in files. |
| K4 | partial | 40 to 800 (760 moves) | Refusal observation with wrong cause, later partial invalid-slot rules; final both-invalid handling/player exclusion incomplete. |
| K5 | partial | 40 to 800 (760 moves) | Some blocked-movement facts, then explicit lock/immobility; wrong spatial cause and selection absent. |
| K6 | correct | 40 to 800 (760 moves) | Current6 becomes red, markers removed, normal movement restored; later rewrites preserve effect. |
| K7 | absent | 1 to 338 (337 moves) | UNKNOWN/alternatives first; leading enemies-present at338; newer target-placement plan358 overrides it; best-fit conserved no-other-plain rule in notes501 and final800. |
| K7 | partial | 358 to 501 (143 moves) | UNKNOWN/alternatives first; leading enemies-present at338; newer target-placement plan358 overrides it; best-fit conserved no-other-plain rule in notes501 and final800. |
| K7 | correct | 501 to 800 (299 moves) | UNKNOWN/alternatives first; leading enemies-present at338; newer target-placement plan358 overrides it; best-fit conserved no-other-plain rule in notes501 and final800. |

## Corrections and remaining uncertainty

The report method notes give the full first-pass correction list: earlier partial K3/K6/K4 evidence, behavioral K6 credit, operational K1 credit, one checkpoint of complete K3, partial rather than wrong K5, and exact quote encoding repairs. All starts and handoffs now match the revised labels.

Most uncertain: K3 belief versus calculation error around100-125; K6 effect equivalence despite wrong conceptual names; K7 universal coverage reading despite unseen orange crates and listed alternative win hypotheses; degree of partial K5 at25/475. These were decided from the rubric rather than from the number of wins.

Initial check_run after report creation: run-H: 7 segments, 25 of 25 quotes found word for word, 0 problems. Final checks are recorded in validation.txt.
