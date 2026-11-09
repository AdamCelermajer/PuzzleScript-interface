# Run-G grading report

## 1. Result

The final model earns **4.5/7 (64.3%)**: three rules correct, three partial, and one wrong. It reports finishing three of six levels and exhausting 800 moves on level 4. Rule knowledge peaked at 5/7 in the checkpoint series, well before the end. Winning and knowing diverged: the third win prompted an incorrect revision of the goal rule, and later play repeatedly applied correct local effects inside an incorrect account of the board.

“End” below means cp039, including the final `world_model.md`. At cp037, after the last move but before that file, the score is **4/7 (57.1%)**. The final file explicitly restates the correct crate-following rule; this is a writing-time change, not evidence of another successful game action.

| Rule | Final belief | Source | First correct evidence; checkpoint recording it |
|---|---|---|---|
| I1: four directional controls | correct | both | after 6 moves; cp000, ending at 15 |
| I2: slide until the next wall, water, or immovable crate | partial | both | after 44 moves, adding water to the earlier stopping model; cp006, ending at 50 |
| I3: push and slide together, player adjacent behind the final crate | correct | both | after 25 moves; cp004, ending at 29 |
| I4: push an entire chain of crates | wrong | both | never adopted correctly |
| I5: water stops the player before entry | correct | both | after 44 moves; cp006, ending at 50 |
| I6: a crate disappears into water, making traversable floor | partial | both | after 51 moves; cp007, ending at 72 |
| I7: stop on the goal; passage alone is insufficient | partial | both | after 18 moves; cp001, ending at 21 |

“Both” at the end means current files and thinking support the label. The final notebook-alone labels equal these combined labels. Earlier, the only file was the move-22 notebook: it scored 2.5/7 (35.7%) throughout cp002–cp037. Its correct stop-on-grass statement did not override newer contrary thinking.

| Requested point | Checkpoint | Combined points | Combined score | Files alone |
|---|---|---:|---:|---:|
| 25 moves | cp003 | 2.5/7 | 35.7% | 35.7% |
| 100 moves | cp009 | 5/7 | 71.4% | 35.7% |
| 200 moves | cp013 | 4.5/7 | 64.3% | 35.7% |
| 400 moves | cp021 | 4.5/7 | 64.3% | 35.7% |
| End, 800 moves and final file | cp039 | 4.5/7 | 64.3% | 64.3% |

Other score changes: cp000/15 = 21.4%; cp001/21 = 35.7%; cp004/29 = 50.0%; cp006/50 = 64.3%; cp007/72 = 71.4%; cp011/150 = 57.1%; cp012/175 = 64.3%; cp032/675 = 57.1%; cp038/800 = 64.3%. I4 changing from absent to wrong at cp016 does not change the numerical score. These are checkpoint scores, not interpolated estimates of every intervening move.

## 2. How it reasoned

Early learning used direct comparisons. It tried each direction, pressed up again against the same boundary, and separated a long slide from a fixed-distance move. After 6 moves it writes, “Confirmed ACTION4 = right.” At move 18, passing over grass without clearing the level supports the discriminating statement, “it only clears when you "stop" on the grass”. After the first crate push it considers alternative implementations but extracts the common observable rule: “the crate slides forward as far as it can, and the player ends up adjacent behind it.” These are adopted conclusions, not merely questions.

Its dominant planning method is to enumerate stopping positions and reason backward from a desired stop. It builds lists of entrances to small clusters, rejects circular routes, and repeatedly concludes a cluster is sealed. This can work when the map and transition model are right. Here, it often treats being able to stand immediately beside a crate as a prerequisite for pushing it, forgets that a longer slide can initiate the push, or gives the player an incorrect endpoint after a correct crate displacement. These errors make the reachability proofs unreliable even when the general slide rule is available.

It also inspects the picture, tile numbers, and pixel descriptions. The text shows repeated row/column indexing corrections. Rather than consistently treating a mismatched prediction as a possible reading error, it often invents hidden state: phase doors, a “machine,” a gravity/drag effect, portals, and random teleports. It then expends moves testing the invented conditions. It uses numerical-looking arguments about open probabilities and periods, but the underlying event counts and coordinates are unstable. The final claimed rates are the player's estimates, not independently verified measurements.

The notebook contributes little during play. `notes.md` stays at level 3 from move 22 until the final write-up at 800; it still calls the yellow crate unknown and undo a random past-position jump. No solver or simulation script appears among the supplied player files. The observed search is prose-based, with lists of routes, repeated coordinate calculations, and extensive retrospective passages. The final `world_model.md` consolidates learning and errors together; it is not a reliable experimental log.

## 3. Turning points

| Move marker / checkpoint | Evidence and consequence |
|---|---|
| after 15, cp001 | First level completion is acknowledged. This establishes grass as a goal, but alone cannot distinguish stopping from passage. |
| after 18, cp001 | Passage over grass fails on level 2; the player correctly concludes that stopping matters. Level 2 completion is then acknowledged at the next level transition. |
| after 25, cp004 | A single push moves the crate from (5,4) to (1,4), with the player at (2,4). It explicitly learns sliding together. This evidence occurs after the cp003 move-25 cut. |
| after 43, cp006 | It acknowledges level 3 completion but interprets its final move as passage over grass. It adopts “If not, push a crate (if one exists), then pass through the grass.” The correct general goal rule becomes partial. |
| after 44–51, cp006–007 | The blue E blocks the player; pushing a crate into it consumes the crate and permits crossing. Calling it a machine does not prevent credit for I5/I6. |
| after 140, cp011 | It adopts a universal passage rule: “So the win condition is: the player passes over a grass tile during a slide.” It also makes incompatible crate-following predictions. |
| cp012, ending 175 | “L2: win = grass stop.” restores a substantial correct case of I7, although the false L3 passage claim remains. |
| after 266, cp016 | “Can't push a crate onto a crate → no movement!! Blocked.” It rules out a chain push with space beyond the leading crate. I4 becomes wrong. |
| around 420, cp022 | A second crate crosses the already-filled tile and reaches (1,4), leaving the player at (2,4). This defeats the proposed second-charge effect and supplies strong evidence for the filled-tile behavior. |
| around 535, cp027 | “So A7 = pure undo (each A7 rewinds 1 action's state exactly).” This corrects a major unscored misconception, although later exceptions are invented again. |
| 654–675, cp032 | A forgotten consumed crate becomes imaginary evidence that an already-charged machine sometimes consumes another crate. I6 becomes partial. |
| 800, cp038 | The final file states the correct player-behind-crate rule explicitly, restoring I3 correct, while recording false doors, chain denial, and conditional goal rules. |

## 4. Where it went wrong and why

**Wrong goal generalization after a win.** At 43 it tries to reconcile the third win with the earlier failed passage test by adding a crate-push prerequisite. At 140 it goes further and interprets stopping in L1/L2 as merely a special case of passage. The later level-specific stop equations recover partial knowledge, but never recover the universal stop requirement. Repeated assertions that level 4's grass is unreachable lead it to search for unrelated winning events. At 552: “The win condition is not the grass. Period.” This is a wrong level-specific rule, but does not erase its retained correct L1/L2 cases. The cost is intertwined with its map and search errors; no exact number of moves can be attributed solely to I7.

**Chain pushing excluded without an adequate test.** Early thoughts consider chains as questions, not an adopted mechanism. By 266, after the first crate has been consumed, the player rejects pushing the two remaining adjacent crates left, even though its own represented (5,4) is empty. At 552 it makes the imported assumption explicit: “In sokoban only one crate can be pushed” and “crates can't push crates.” This persists into the final file. It repeatedly declares the remaining crates frozen and seeks doors or resets instead. The supplied text supports lost opportunities and constrained search, but not an exact counterfactual solution length.

**Coordinate errors become movement laws.** After the first fill, a misread downward endpoint becomes “E pass-through: Up = free, Down = −1 cell (permanent)” in cp007. Later, the player forgets which column it started in and explains ordinary movement as teleportation. Around 308 it treats the start as (8,2) despite having just returned to (8,4), then attributes arrival at (1,4) to an anomaly. It also misreads the crate/player endpoints around 164 and 178 as passage through a supposed door. At 575 ordinary arrival at a floor stop becomes evidence that a phase door has opened. I2 remains partial: ordinary straight sliding and stopping are understood, but the invented exceptions alter predictions for ordinary cases. Some individual observations are only available through the player's description; I do not claim to reconstruct every actual board or action.

**Correct crate mechanics inconsistently applied.** From cp011 the player repeatedly gives the crate its distant final position while leaving the player near first contact. For example: “crate (8,8); player (8,5)!!! A new stop (8,5)!!!” It uses these imagined stops in subsequent route reasoning. At 249 it explicitly divides an unobstructed push into two actions. Later correct examples coexist with renewed errors, including the two-stage feed prediction around 466 and 529. I3 partial records this mixture. It is the most uncertain judgment: some occurrences could reasonably be treated as planning/calculation failures with an intact abstract rule. The final file resolves the local rule clearly: “the player stops on the tile behind the crate's final position.” Chain denial is scored separately under I4.

**Forgetting an object is gone creates a new water rule.** At 640–641 it notices that the first crate was consumed. At 654 it nevertheless plans another push of that crate, sees the player at (1,4), and concludes the filled machine consumed it again. It later says, “the consumption of the crate at (5,4) at 27 is now the normal behavior”. No second crate was established in that position by the stated preceding sequence. After a detour, the same mistaken premise appears to refute a push-distance hypothesis. It then proposes aging, random outcomes, and phase-dependent consumption. This contaminates I6 while preserving the correct first-consumption and player-crossing effects. Roughly 719–759 is spent shuttling to age this supposed state; subsequent undo/replay loops through about 774 repeat it. These are overlapping experiment windows, not an additive estimate of all wasted moves.

**Undo and history arithmetic.** The early random-rewind model becomes a two-action rewind model around 76 and is retained after full-state restoration is noticed around 165. Around 213–227 it tries to return to a named historical index using that arithmetic, then abandons the attempt. It learns pure one-action undo around 535, but later imagines that undo can restore a consumed crate while preserving charge from a nonexistent later consumption event. Around 715, direct evidence that undo reverses the fill is acknowledged, then explained away to preserve the imagined later event. Undo is outside the seven-rule score but materially affects search and memory claims.

The failure therefore combines incorrect rules, inaccurate state tracking, and planning errors. It is not simply an inability to plan with seven correct rules. Conversely, substantial local knowledge was present: controls, water blocking, and the first-fill effect were useful long before play ended. Its tendency to abandon the goal route too early and preserve unsupported hidden-mechanism theories too long helps explain the prolonged stall.

## 5. Stuck stretches

No further level completion is reported after move 43: **757 subsequent budget moves** remain on level 4. This does not mean every one was uninformative; it includes the first water fill, later crate rearrangements, and the undo correction.

The recurring pattern is more specific than mere repetition. Around 100–200 it tests supposed phases and portals while increasingly declaring the goal region sealed. Around 203–227 it alternates corridor retries with a failed historical rewind. From roughly 236–400 it returns to corridor/portal tests, resets, and short “early window” sprints; failed windows cause new timing explanations instead of abandonment of the claimed portal. Around 401–425 it makes a useful crate rearrangement and observes passage across filled water, but then loses the route that produced it. By 552 it cannot reconstruct how it previously moved the middle crate and attributes its own past success to a possible anomaly.

From roughly 553–632 it tests supposed exits and doors. Around 641–675 it pursues undo/feed and correlated-door experiments. Around 683–695 it retries a corridor; around 719–759 it deliberately shuttles to age the machine; around 760–774 it repeats undo/push cycles; the last stretch, about 784–800, again tests the same corridor. The player's counts such as “50” corridor tests are not reliable independent totals: labels drift between different cells and the action accounting is often off by one. The quoted windows are directly visible in checkpoint thinking and should not be summed as separate causal costs.

## 6. Effect of its memory

There is **no explicit conversation-restarted marker** in the 40 checkpoints. Therefore I never reset thinking-only labels. The supplied files do not independently reveal actual compaction summaries, so I cannot identify a precise causal effect of a particular compaction.

There is nevertheless direct evidence of stale retrospective state. At 228 a summarizing passage refers to a state around 198; at 441 another refers to 421; at 665 another describes action 635, while the following ordinary thinking at 666 resumes at the more recent position. These passages occur in the thinking stream. They should not be treated as authoritative external summaries or as restart notices.

The visible costs are repeated reconstruction and promotion of misremembered states to evidence. The player forgets a middle-crate route it used earlier, forgets which crate was consumed, and repeatedly relies on old claims of corridor openings. At 140 it says, “I'll trust the notes: it was passing over grass.” The actual current notebook says to stop on grass. This is a concrete conflict between remembered documentation and the provided file, not evidence that the file itself taught the false rule.

Because the notebook is unchanged for most of the run, it neither preserves the learned water/crate facts nor records corrected coordinates and rejected mechanisms. The final world model arrives after the moves are exhausted and preserves many mistaken conclusions. The text supports a memory/state-tracking contribution to failure; it does not support a numerical estimate of loss caused by context management alone.

## 7. Method notes and skeptical review

I read every checkpoint in full, in order, used both current files and thinking, saved labels after each checkpoint, and checked each segment. Only this run, the common rubric, and the user-authorized grading scripts were used. There was no source-code/gameplay lookup, access to other runs, service operation, or commit. All grading writes stayed inside run-G.

The mapping is behavioral: E/machine at (3,4), which blocks the player and consumes the first crate, is water. Earlier gray objects 19/20 are fixed blockers, not evidence of water knowledge. Calling water a machine is not itself an error. I6 initially earns correct because the complete observable fill-and-cross effect is adopted, despite speculation about additional charges or doors. The late partial label reflects the adopted claim that the filled tile still consumes crates under unknown conditions. An immovable crate's effect on a distant slide is evaluated under I2; chain denial under I4. Neither automatically removes I3 credit for the single moving-crate case.

Checkpoint boundaries matter. The first complete push explanation is in cp004's thinking marked after 25 moves, not in cp003. The requested move-25 score therefore uses cp003 without borrowing the later explanation. First-correct times in the rule table use the thought markers, while the score table uses checkpoint endpoints. Some player action counts disagree with those markers; I use the supplied markers and qualify approximate experiment windows.

Initial absent labels cannot be proved by a positive quotation. Their required notes quote the initial board description or an explicitly untested goal question; the absence judgment comes from reading all of cp000. Silence thereafter is not forgetting. Questions about chains do not earn knowledge, and a chain stopped by a wall beyond its leading crate does not establish a false anti-chain belief.

### Changes made during the audit

- **I3 cp011–cp014: correct → partial.** The provisional downgrade began at cp015. Earlier asserted crate/player endpoints already conflict with sliding together and are used in route reasoning. I moved the onset to cp011 and removed the redundant change note at cp015. The first-correct time remains 25; the explicit final statement still restores correct at cp038.
- **I7 cp012–cp037: wrong → partial.** I had overextended the universal passage claim at cp011. The later explicit “L2: win = grass stop.” and repeated L1/L2 stop equations restore a substantial correct case. Rejecting grass only for L4 does not erase those earlier-level beliefs. Accordingly, cp038 records rather than newly recovers partial goal knowledge.
- Replaced generic initial absent-label notes with quotations showing the initial object-description scope or the untested goal question. Updated affected handoffs and carry-forward evidence.
- During the initial reading, before saving the later checkpoint trajectory, I removed a tentative water interpretation of an early gray blocker. I5 stays absent until actual E/water evidence in cp006.

### Coverage of the retrospective audit

Every transition to correct or wrong was rechecked in surrounding text: I1 at cp000; I7 at cp001; I3 at cp004; I2/I5 at cp006; I6 at cp007; I7 wrong at cp011; I4 wrong at cp016; and I3 correct at cp038. The audit also rechecked the partial transitions, especially the final-file ordering.

For every belief held longer than 100 moves, I reviewed both its onset and later supporting/contrary passages: I1 correct through the final controls; I2 partial from cp007 through the phase/anomaly and blocked-push claims; I3 partial from cp011 through repeated wrong endpoints and the final replacement; I4 absent through cp015's conditional/pinned-chain cases and wrong from cp016 through cp038; I5 correct from cp006 through pre-charge blocking; I6 correct from cp007 through the second-crate crossing at 420, then partial from cp032 through the final consumption claim; and I7 partial from cp012 through explicit L1/L2 stop equations and the final file. The long-lived notebook labels were separately rechecked against unchanged `notes.md`; the final new file takes precedence where the two files disagree.

**Least certain:** I3's extended partial interval, particularly its onset at cp011, is sensitive to treating repeated adopted endpoint predictions as beliefs rather than planning slips. I7 wrong at cp011 is also borderline: it explicitly adopts a universal passage rule, then recounts L1's historical stopped win; I treat the latter as compatible with its false universal account, whereas cp012's L2-specific stop equation reinstates partial credit. I6 partial after cp032 is less uncertain but depends on treating “becomes floor” as excluding the model's later crate-consuming effect. Giving I3 correct throughout its disputed interval would add 0.5/7 (7.1 percentage points) there, including moves 200 and 400; it would not change the final table.

Final validation after the retrospective audit:

```text
seg-0: ok: 6 checkpoints x 7 rules
seg-1: ok: 5 checkpoints x 7 rules
seg-2: ok: 9 checkpoints x 7 rules
seg-3: ok: 11 checkpoints x 7 rules
seg-4: ok: 9 checkpoints x 7 rules
run-G: 5 segments, 20 of 20 quotes found word for word, 0 problems
```

Supplementary checks verified the rubric's strict 20-word quote limit, carry-forward `start.json` contents, handoff lengths, and report quotations. Two report quotations had sentence punctuation inside the quotation that was not in the source; that punctuation was moved outside. No further label changes followed the final retrospective review. The script validates structure and quotation presence, not the substantive judgments discussed above.
