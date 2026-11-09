# Run L: rule learning through 437 moves

The player finished all six levels, but its final rule model is not fully correct. Six rules are correct and the chain rule remains partial: it understands an already contiguous chain, while still saying that another crate encountered during movement stops it. The final combined and notebook-only scores are both **92.86%**. Completion therefore does not establish complete rule learning.

## Result

| Rule | Final belief | Source | Notebook alone | First correct checkpoint (move) |
|---|---|---|---|---|
| I1: four cardinal controls | correct | both | correct | cp-000 (1; adopted in thinking before the first move) |
| I2: slide until blocked | correct | both | correct | cp-000 (1) |
| I3: contact pushes a crate; player follows it to its stopping point | correct | both | correct | cp-005 (29; push observed at 28) |
| I4: a moving crate pushes another crate it encounters; the chain moves together | partial | both | partial | cp-056 (393), briefly; subsequently lost |
| I5: unfilled water stops the player | correct | both | correct | cp-011 (54) |
| I6: a crate disappears into water, opening the tile for continued sliding | correct | both | correct | cp-008 (48) |
| I7: finish the move resting on the goal, rather than merely crossing it | correct | both | correct | cp-002 (12), implicit in the adopted route; explicit failed crossing at 17 |

“First correct” is the first saved correct checkpoint, not a claim of permanent retention. Checkpoint boundaries and individual thinking markers sometimes differ by a move. For example, the cp-002 route was planned after move 7 and deliberately crosses the goal before returning to stop there. Later evidence is much less ambiguous.

Scores use all seven rules, with correct = 1, partial = 0.5, and wrong/absent = 0. The last checkpoint at or before each requested move is used, including later thinking or file writes at that same move.

| Move | Checkpoint | Combined points / 7 | Combined score | Notebook-only score |
|---|---|---:|---:|---:|
| 25 | cp-004 | 3 | 42.86% | 35.71% |
| 100 | cp-014 | 6.5 | 92.86% | 78.57% |
| 200 | cp-024 | 5.5 | 78.57% | 64.29% |
| 400 | cp-061 | 5.5 | 78.57% | 92.86% |
| 437, end | cp-068 | 6.5 | 92.86% | 92.86% |

At 25 the correct rules are controls, sliding and stopping on the goal; the crate is still treated as a wall. At 100 the only remaining combined deficit is the chain rule. At 200 and 400 the player has additionally rejected the actual win condition. At 400 its thinking is worse than its files: it has revived a pass-through/timing account despite a correct saved goal condition.

## How it reasoned

The player initially measures image tiles, compares bevels and dark centres, and reconstructs a numbered grid. It correctly distinguishes the early dark wall tiles from later blue objects; the early speculation about “holes” does not demonstrate knowledge of water. It then builds a graph of stopping positions, manually enumerates routes, and writes breadth-first search programs with increasingly elaborate movement models.

Its strongest learning comes from comparing a specific predicted move with the resulting state. Move 28 shows that a distant crate moves and the player follows it. Moves 47–48 show that the crate disappears, the blue object changes into passable “gold,” and sliding continues. At 54 it accepts that the unfilled blue tile blocks the player: “Accept: the wave is a permanent wall to the player.” The theme names are inaccurate, but these effects map to the actual rules.

Its weakest recurring inference is to convert a failed route search into a new rule. An omitted reachable position, incorrect map coordinate, or faulty simulator produces “impossible”; that conclusion then motivates a special win condition, timer, movable blue tile, or altered control mapping. It often re-enumerates substantially the same geometry without repairing the premise. Questions and lists of possibilities are not graded as adopted beliefs; categorical conclusions and chosen plans are.

Notes help, but accumulate contradictory history. Old `state.md` still calls crates walls after an appended correction explains pushing. Old solver files continue to treat blue as movable while newer notes explain absorption. Later `l5.md` and `l5session2.md` mix correct observations with false “sealed” positions and supposed dynamic changes. I give explicit corrections and the latest operative plan precedence over obsolete passages. Code earns rule credit when its transition logic actually expresses the rule; a search reporting no solution is not evidence that the true game is unsolvable.

## Turning points and level completions

| Moves | What changed |
|---|---|
| 7, 12 | First two levels completed using sliding routes. The second route distinguishes crossing the goal from ending on it. |
| 17–43 | Crossing the third goal fails at 17. ACTION7 is eventually recognised as undo. The move-28 crate experiment corrects the wall belief; planning two crate pushes enables completion at 43. |
| 47–100 | Crate absorption and passable residue are learned; direct blue contact establishes blocking at 54. The fourth level ends at 100 after correcting reachable-state reasoning. |
| 106–150 | A pair of crates fills two water cells. The player misreads their changed state as evidence that blue is intrinsically passable. Later blocked approaches restore the distinction between unfilled and filled cells. |
| 228–243 | The player finally separates a crate pair rather than always feeding both water cells. One crate fills the near cell, while the far water remains a blocker. The player stops on the goal and wins the fifth level at 243. |
| 393 | A full 41-action fresh-state plan is reasoned out, with explicit automatic contact pushing and chain recognition. It is not executed. The following continuation loses this plan. |
| 404–405 | Simulator debugging replaces false movement and floor assumptions. A search produces a stored 32-move plan with predicted states, and the player resets. |
| 406–437 | The stored plan is followed and checked step by step. The final crate stops at (10,5), leaving the player on the goal at (9,5). Completion of all six levels is reported at 437. |

The fifth-level breakthrough is a planning correction using already available mechanics. At cp-027 the player recognises: “But "stop on the goal" is the primary victory condition”. Its earlier insistence that both crates must be sacrificed was the obstacle. The successful layout keeps water at (5,7) unfilled while clearing (5,5), so that the player stops at (5,6).

The last level needs two crates to open two water cells and a third to provide the final stop. The executed 32-move plan first reserves the lower crate by moving it through (6,4) to (6,12). The upper pair clears water at (3,6), with the survivor routed through (4,3) and (4,5) into water at (5,5). The reserved crate then travels via (3,12), (3,3), (4,3), and (4,5), before being pushed down to (10,5). This leaves the player at (9,5). These are the player's recorded plan and observed execution, not a grader-run solution.

## Wrong beliefs, duration, and consequences

Durations below describe checkpoint intervals, not exact counts of moves caused by a belief. A long window can contain several temporary revisions. Causal move costs cannot be isolated from simultaneous map and planning errors.

* **Crates as fixed walls:** cp-003–004, moves 13–25, corrected by the push observed at 28 and saved at 29. It made the third level appear sealed and encouraged speculation about special ACTION7 powers. The entire 13–29 interval should not be counted as pure wasted cost; it also contains experiments that resolved uncertainty.
* **Blue as movable or already passable:** first adopted at 44, corrected at 54; revived at 107, corrected by 150; revived after the second restart at 244, corrected by 268. The 107 error comes from conflating filled cells with their unfilled predecessors. At 150 the player states that “each arm is solid until its own crate is absorbed, and after that it becomes passable.” After the restart, old movable-blue code and the apparent design of the goal support the false blue-push plan again.
* **A special win condition:** wrong at checkpoints 125–225, restored at 243; wrong again at 244, briefly restored later at the same move, then wrong at 247–300 and restored at 316. It also rejects stopping on the goal at 333 and 400–404, restoring it at 334 and 405. These are repeated reversals, not one continuously unknown rule. At 125 it says, “The win must be a pass-through or state condition.” By 212 it counts 29 unsuccessful goal crossings, explores timing and directional sequences, and briefly mistakes an empty-row slide for a crate destruction before retracting that claim. The failed pass counts, resets, and undo tests are visible costs; no defensible total separates them from other exploration.
* **Pushing only from an adjacent starting square:** repeatedly partial at 171–175, 244–300, 329–330, 334–360, 392, 394–395 before the new solver, and within move 404. The player knows that crates move and that it follows them, yet repeatedly invents a stopping point before a movable crate, or demands an unreachable adjacent position before a push. This makes useful routes appear impossible. The audit restores correct I3 at 331–333 because late explicit contact-push statements and distant-push predictions supersede earlier mistakes. At 393 it explicitly says the “player can start at (2,5); no need to stop at (3,5).” At 404 it finally diagnoses the same error in its simulation: “In the actual game, the player pushes the crate when it reaches it during a slide.”
* **Crates block one another:** the early solver handles initially contiguous chains but stops at an additional encountered crate, so I4 stays partial for a long interval. Later thinking sometimes denies even contiguous pushing: at 354, “So the crates (3,9) and (3,10) are stuck (they block each other).” Similar adopted claims recur at 392 and 404, despite intervening observed pushes. The explicit chain recognition at 393 earns correct briefly. The final notebook again says a group runs “until the lead crate hits a wall or another crate”; its general chain rule remains incomplete.
* **Wrong control mapping:** at 322–323 it adopts diagonal quadrants and the longer available direction, based on a mismatched recollection of an earlier action and position. It calls this “confirmed,” then a direct test refutes it and standard cardinal controls return at 325. This is a short but clear example of state-memory failure creating a false rule.
* **Stopping too early after a water interaction:** at 334 and 356 the player predicts either stopping where the consumed crate was or stopping a crate just before water. Correct continuation returns at 347 and 360. A similar partial regression appears within move 404 and is repaired in the next thinking-only checkpoint. The disappearance effect is retained, hence partial rather than wrong for I6.

The final chain gap and occasional imprecise wording about standing behind the *lead* crate are real limitations. I3 remains correct because its single-crate content is consistently stated; the chain-position and newly encountered crate defects are handled under I4. The final uncertainty about whether several water cells can be filled in one push is an open question, not an adopted contrary rule.

## What the long thinking stretches achieved

The checkpoint thinking sections contain about 4.39 million characters, of which about 2.96 million occur from cp-028 onward on the final level. These counts include thinking-section separators and are character counts, not tokens or elapsed time. They exclude the repeated notebook sections.

The final level occupies moves 244–437. Much of its long thinking re-counts the same grid, declares the goal inaccessible, promises a RESET without issuing it, and then starts the same reasoning again. cp-051 and cp-052 together contain over 280,000 file characters around moves 354–356; cp-062 contains about 200,000 at 400–404. Large text volume here often produces neither new observations nor a stable improved rule model.

There is useful work within these stretches. It repeatedly reconstructs the route that moves a crate from (3,3) through (4,3) to (4,5), learns from the separated-crate encounter around 378, and produces the unexecuted 41-action plan at 393. But it does not reliably preserve those gains. It also invents an extra grid column, misplaces walls, forgets consumed crates, rewinds its remembered action count, and interprets a previously moved crate at (2,4) as a new spawn.

The decisive change at 404 is validation of the simulator against a known transition. The player notices that its code treats a distant crate as a wall, fixes contact pushing and group continuation, and discovers that original player/crate cells were still being treated as blocked terrain. Debugging also addresses tuple handling and path reconstruction. Once the transition model and map are usable, search finds the stored 32-move plan. Execution with predicted states, rather than further ungrounded geometry, finishes the level. This does not prove that every detail of the simulator was correct: its chain model still had a documented gap.

## Memory and restarts

The explicit restart markers occur at cp-015 (101), cp-028 (244), and cp-056 (393). I applied the rubric's reset of thinking-only persistence at these markers, keeping claims supported by files or restated in the new material. A marker is a checkpoint-level boundary, not a precise timestamp for every sentence in that window.

After the first restart, core mechanics are restated, so there is no immediate broad knowledge collapse. Level numbering soon becomes confused: the four-water fifth level is repeatedly called “L4,” and the final level “L5.” The report uses actual completion order to avoid perpetuating that mistake.

The second restart is more damaging. The successful one-crate/remaining-water fifth-level insight is not preserved as a clear solved-level account. The next continuation reopens blue pushability, adjacent-only pushes, and alternative win rules. Files contain old theories as well as corrections, so merely having a notebook does not guarantee that the right claim is recovered.

Around the third marker, cp-056 reconstructs an explicit 41-action solution and correct chains, but cp-057 starts from a different remembered state and abandons that route. This is visible loss of an actionable plan, not just silence about a rule. The later crate-at-(2,4) “spawn” interpretation and repeated stale action counts provide further evidence of state-memory problems. There is no clean counterfactual move cost: the record shows re-derivation and wrong experiments, but not how quickly the unused plan would actually have succeeded.

## Method notes and audit

All 69 checkpoints in 21 segments were graded, with the predecessor's cp-000–008 labels used as the starting point. Remaining checkpoints were read in full, sequentially, including long thinking, and labels were saved checkpoint by checkpoint. Only the permitted run folder, rubric, and grading scripts were used; no game source, other runs, gameplay, services, Docker, or commits were involved.

The final review checked all 40 transitions to correct/wrong against their quoted context, and all nine uninterrupted combined-label intervals spanning more than 100 moves against intermediate text as well as endpoints. `audit.md` records the review. File-only grades are independent of thinking persistence. Within NEW VERSION notebooks, an explicit updated correction or latest operative plan supersedes stale copied material; conflicting current claims are treated cautiously.

Audit changes: I3 at cp-043, cp-044, and cp-045 changed from partial to correct, with source thinking and notebook still partial. The final cp-043 summary explicitly adopts automatic contact pushing; late cp-044/045 examples also push across a gap. Earlier adjacent-position route mistakes should not override those later statements. cp-046 then explicitly predicts a stop before the movable crate, so its partial label remains, now with a transition quote. I also repaired two arrow-corrupted quotes (cp-029 I3 and cp-052 I6), replaced weak evidence excerpts at cp-002 I7 and cp-055 I3 with more direct exact quotes, replaced cp-029 I7's speculative excerpt with its later adopted plan, and refreshed segment starts and the affected handoffs. No requested sample score, final label, or first-correct checkpoint changed. The predecessor's belief labels were retained after review.

Least certain are the implicit first correct I7 at cp-002; I5's adopted blue-push account after the second restart; the boundary between a bad route calculation and an adjacent-only pushing belief in long I3 windows; and I7 around cp-025, where a rejected stop condition is reconsidered among several alternatives. I4 partial is deliberately not a penalty for failing to state a quantifier: both early code and the final note explicitly predict that a newly encountered crate blocks motion. Conversely, statements of a correct single observed case receive correct when they do not contradict the general rule, as requested.

Three main findings: correct mechanics can coexist with severe search and state-tracking failure; discoveries repeatedly regress when the player loses its place or follows stale notes; and a validated simulator plus an explicit execution plan finally converts partial rule knowledge into a completed run.

Final validation: all 21 segment checks pass; every evidence note also passes a separate strict 20-word check. The requested whole-run command reports:

```text
run-L: 21 segments, 67 of 67 quotes found word for word, 0 problems
```
