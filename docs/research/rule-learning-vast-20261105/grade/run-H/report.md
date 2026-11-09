# Run H: rule learning and reasoning

Run H ends with **4.5/7 rule points (64.3%)**, with five partial rules and two correct rules. It clears two levels, at moves 377 and 418, and uses all 800 moves. These are separate outcomes: the later failure does not mean it has no correct rules, and the two wins do not validate its model of the controls or movement.

The decisive limitation is its failure to retain and generalize the landing-choice mechanism. It calls the red crate a “goal,” the blue target an “item,” and the two landing markers “enemies.” Those names alone are harmless. The harmful beliefs are that the solid marker has a largely fixed destination and that the markers prevent movement through spatial blocking fields. Its search consequently excludes legal destination choices. Coordinate mistakes and stale memories then make that restricted search look like a proof of impossibility.

## Result and score over time

“First correct” below means the first **checkpoint** awarded correct, not a claim that the discovery occurred precisely on its last move. K3 loses full credit at checkpoint 008; K1 loses it at the marked restart at move 299.

| Rule | Final belief | Final source | First correct checkpoint move |
|---|---|---|---:|
| K1: four directions; ACTION5 confirms a choice | partial | both | 75 |
| K2: walls; ordinary one-cell crate pushing and obstructions | partial | both | never |
| K3: enter red's old cell; red has two forward knight landings | partial | both | 100 |
| K4: landing must be free; no valid landing refuses the push | partial | both | never |
| K5: direction keys select a displayed landing; player stays still | partial | both | never |
| K6: ACTION5 places red at selected landing and resumes play | correct | both | 40 |
| K7: every target covered by a crate wins | correct | both | 475 |

The final notebook labels equal the final combined labels. There is no observed ordinary orange-crate encounter. K2 earns partial for walls; the early “dark box” is the target, not evidence about ordinary crate pushing.

| Move | Checkpoint | Combined points / 7 | Combined score | Files alone |
|---:|---:|---:|---:|---:|
| 25 | 002 | 3.0 | 42.9% | 21.4% |
| 100 | 007 | 4.5 | 64.3% | 50.0% |
| 200 | 011 | 4.0 | 57.1% | 50.0% |
| 400 | 024 | 4.0 | 57.1% | 57.1% |
| 800, end | 047 | 4.5 | 64.3% | 64.3% |

At checkpoint 014, move 275, the score is 4.5/7 (64.3%). The restart checkpoint at 299 falls to 3.5/7 (50.0%). The final score is unchanged from checkpoint 029, move 475, through the end. Neither a long trace nor additional moves guarantees additional rule knowledge.

## How it reasoned

Early experiments decode the four directional buttons, then compare entry into the red object, ACTION5, blocked moves, and undo. The notebook at move 13 already records a genuine red-crate transition: “goal vanished, player took spot; 5 spawned (2,6), 6 spawned (4,6)” and then “5 & 6 vanished; goal 3 spawned at (4,6).” These are partial knowledge even though the surrounding interpretation remains unsettled.

Its strongest reasoning uses a before/after grid comparison or a controlled undo. At thinking marker 26 it recounts the grid and explicitly corrects its assumed movement: “The player did NOT move up at #24!” This separates the marker change from player displacement. Around move 51 it explains how an up/down press toward dashed 5 swaps 5 and 6, and plans to press ACTION5 after that swap to obtain the desired red position. At 91 and 100, vertical entries establish the same two-forward, one-side geometry already observed horizontally. I credit this structural knowledge at checkpoint 100. At checkpoint 125, however, it adopts a route that puts the pair at (3,4)/(5,4) after a westward entry into (2,6), contradicting the two-plus-one rule. K3 becomes partial again; later mixed and incorrect applications never establish a stable complete correction.

Much of the remaining thinking takes the opposite direction: it elaborates a rule to fit a mistaken board reading. A stationary player is treated as having walked, then as having been pulled back. A hidden target is treated as collected or destroyed. A failed push is assigned a special opening side rather than checked against both landing cells. It frequently enumerates candidate explanations, but then relies on one as if experimentally settled before resolving the original observation.

The player constructs long reverse-reachability chains in prose, often with explicit coordinates, approach sides, and expected marker positions. It repeatedly reverses “side approached from” versus “direction moved,” changes signs, or uses a one-row shift where it just stated a two-row shift. These are visible planning and state-tracking errors in addition to wrong rules. There is no player-authored executable search script in the supplied files; the available working memory is notes.md, later plan.md, and finally world_model.md. Claims such as “all verified” in those files are the player's claims, not independent validation.

## Turning points

| Moves | Evidence and consequence |
|---|---|
| 8–13 | Red entry puts the player on the old red cell; ACTION5 makes red at solid 6. First concrete pieces of K3/K6. |
| 26–40 | Recounting disproves imagined movement. Undo is understood. The move-40 notebook explicitly ties ACTION5's red location to the current 6 and says movement is possible after markers clear. K6 becomes correct. |
| 51–100 | A deliberate marker swap followed by ACTION5 gives operational choice/confirmation knowledge (K1 correct by 75). Vertical observations complete the knight geometry (K3 correct by 100). The player still explains immobility using enemy blocking, so K5 remains partial. |
| 150 | Testing both sides of the same red instance using undo undermines a single random opening. It connects entry refusal to wall-invalid landing cells. Later thinking does not reliably preserve this explanation. |
| 225–275 | It adopts carry-item-into-goal as the objective. A successful such entry at about 260 does not win. It then concludes: “the real goal of level 1 = "move the goal to (3,6)"”. This is correct coverage for the one-target case, so K7 becomes partial. |
| 299 | Explicit conversation restart; the retained move-40 files do not preserve the best later thinking. K1 reverts to partial and K7 to absent; K3 was already partial. |
| 329–358 | A false coexistence reading promotes “enter a goal while an enemy is present.” Testing fails; plan.md instead adopts placing red on the target, with an unnecessary subsequent entry. |
| 377, 418 | ACTION5 completes the first and second levels. The player has found successful placement sequences, but still misunderstands selection and initially interprets covered targets as permanently consumed. |
| 448–475 | Leaving a target exposes it again, correcting permanent consumption. At thinking marker 469 it adopts “6 on plain item + 0 other plain items + ACTION5,” with held targets distinguished from uncovered ones. K7 is correct by checkpoint 475. |
| 518–526 | A peek rejects the distance-based opening rule. It does not restore directional choice. After another peek and undo, it declares exploration finished at 526. |

## Wrong beliefs that mattered

Durations below describe visible belief episodes or checkpoint bounds. They are not invented estimates of moves that an optimal player would have saved. Except for the final parking interval, the text does not isolate an exact move cost for each misconception: experiments, navigation, and several false assumptions overlap.

**Targets are solid, carried, or consumed.** At move 13 the notes call the dark target solid, based on a move actually made while choosing. At 43 the player can stand on it and sees its tile disappear. It interprets this as carrying, then respawning on departure. Carry-entry is repeatedly *tested* from this period; the unambiguous adopted victory belief is at 225: “The most natural win condition: enter the goal while carrying the item. Let's go with that.” It is contradicted by the successful entry around 260 and replaced within checkpoint 275. The explicit wrong checkpoint episode runs 225–250; the causal exploration lasts longer. This directs substantial routing toward a false objective but cannot be assigned an exact independent move cost.

A related consumption interpretation recurs around 398–448. The player has seen an uncovered target reappear, but after misreading its own position again treats a vacated target as permanently gone. At 448 it corrects this to targets conserved in plain or held form. This correction is necessary for the later correct win predicate.

**Red has a special opening side.** By 51–75 it is using an effectively random single-side theory. At 150 a controlled comparison provides a better wall-landing explanation; summary-like passages at 173 revive the old theory alongside newer information. After the restart, the rule becomes the side opposite an item's secondary axis, then a maximum-distance rule. It is recorded as verified at 338 and retained in the later notes until the explicit rejection at 518. These beliefs require unnecessary side probing and enter the reverse-reachability arguments. The broad episode is roughly 330–518 after the restart, with earlier predecessors; precise exclusive move cost is not recoverable.

**Landing markers are blocking enemies, rather than a choosing interface.** The move-40 notes say an enemy blocks its entire row and a 3×3 neighborhood. Later versions add a free step followed by “pullback T+2,” quadrant blocking at about 469, and finally all rows within three of an enemy. At 480 it does recover the true effect: “While an enemy is alive, the player can't walk.” This earns partial, not wrong, for K5: the observable immobility is right, the cause and use of directional input are not. Before the restart it had used directional swaps; afterward it does not recover a useful general selection procedure. The final file even concludes “ACTION5 immediately after entry is the only useful continuation.” That excludes the omitted choice action at exactly the point where it is useful.

**Enter red while enemies are present to win.** This becomes the leading hypothesis at thinking marker 329 and is the notebook's “Top idea” at checkpoint 338. Attempts around 354–358 fail and the newer plan replaces it with red-on-target. The explicit episode lasts roughly 29 moves, some spent arranging a supposed coexistence state. Its premise came from misreading positions, not a newly observed win condition.

**The third level is impossible.** The player starts developing this conclusion during the long third-level analyses after move 418 and repeatedly strengthens it through 525. It fixes the solid-6 destination, excludes the other displayed candidate, and then works backward from target (4,5) to show its imagined predecessor graph has no usable entry. Some predecessor calculations are wrong even under that model. At 518 it retracts an opening rule but does not rebuild the search with actual landing selection. The final “CLOSED. QED.” is therefore a conclusion about an incomplete and internally unreliable model, not a demonstrated property of the game.

This final failure combines **wrong rules, poor state/coordinate tracking, and stopping exploration too soon**. It is not simply inability to find a long plan while holding all relevant rules correctly. The distinction between a planning error and a replacement rule is difficult for K3: a single corrected arithmetic slip does not erase knowledge, but adopted routes that repeatedly predict the wrong landing pair prevent full credit. Correct local transitions still earn partial.

## Stuck stretches

No level is cleared before move 377. The early stretch cycles through carry-entry tests, entry-side probes, supposed enemy zones, and rederivations. Around 150–260, extensive prose search repeats paths and “lottery” calculations while the objective and refusal explanation remain unstable. After restart, about 78 moves elapse from 299 to the first win, including repeated investigation of previously seen facts; the trace does not establish how many of those were avoidable because of memory loss alone.

After the second win at 418, the large windows through 475 contain lengthy reachability proofs and competing win conditions. Some genuinely useful learning occurs, especially target conservation and the no-uncovered-targets predicate. But the player keeps using its supposed impossibility result to motivate ever more remote destruction, timing, and multi-enemy mechanisms instead of reopening destination choice.

At thinking marker 526 it says “the meaningful work is done” and records “274 actions remaining.” Moves 527–800 are explicit safe parking shuttles, principally between (5,2) and (5,3). This is a direct, countable cost: **274 remaining actions are spent without further exploration or a third level win**. The repeated thinking and the final file maintain the same conclusion; there is no late recovery hidden inside the parking stretch.

## Memory

Checkpoint 015 explicitly marks the conversation ending at move 299. I apply the restart at that window's end: thinking before the boundary does not count unless present in the files or restated afterward. The notebook then is still the move-40 version. It retains basic controls, blocking observations, and ACTION5's effect, but misses the operational selection knowledge, later jump examples, and leading red-on-target objective. K3 was already partial before this restart; the scored losses are K1 and K7. These account for the score falling from 64.3% at 275 to 50.0% at 299.

The next conversation visibly repeats target passability/hiding and entry investigations, then invents the enemies-present objective. That is evidence of memory-related regression, without proving an exact counterfactual move loss. The retained files also transmit confident errors: the newer session treats old incorrect observations of blocked attempts as evidence when faced with conflicting new results.

There are additional summary-like passages, particularly around 173 and 501, that refer to stale states. At 501–509 undo is reconsidered as though it were unfamiliar despite extensive earlier use. These are visible continuity problems, but the supplied checkpoints do not label further conversation restarts. I did not erase beliefs at those points merely because the prose resembles a summary. Later notes preserve older contradictory appendices and the old plan; explicit newer corrections take precedence.

## Method notes and skeptical review

I read all 48 checkpoints in full, in segment order, including all repeated parking turns, and saved labels after each checkpoint. Grading used only this run's supplied text and true-rule list, the study instructions, and the named preparation/checking workflow. No other run, game source, live game, output directory, or earlier study result was used. Seven segment handoffs and carried start labels have been updated to match the audited labels. The detailed transition and long-hold audit is in [audit.md](audit.md).

The skeptical review changed the first pass substantially:

- K3 and K6 get partial credit from checkpoint 001 rather than 002: the early notebook already records the relevant one-case transitions.
- K4 gets partial at 002 rather than 005, and the move-40 notebook also earns partial. A correct refused-move observation with the wrong cause meets the rubric's explicit partial criterion.
- K6 becomes correct from 004 onward. “Clear enemies” followed by red at current solid 6 and resumed movement is behavioral confirmation; requiring the word “selection” had been too strict.
- K1 is correct at 006–014, and K3 at 007. Deliberate swap-then-ACTION5 use and the generalized two-plus-one geometry were under-credited. Reviewing the proposed longer K3 upgrade exposed contradictory adopted routes beginning at 008, so I retained partial there and afterward. K1 reverts to partial at the explicit restart because the files preserve less.
- K5 is partial from 002 onward. Initial swaps and later blocked-movement effects are substantial correct parts, despite wrong timing or cause. I removed first-pass wrong episodes, including the quadrant interpretation at 029, rather than inconsistently crediting one wrong-cause blocking model but zeroing another.
- Nine label quotations had encoding substitutions introduced when saving the first pass. They were repaired or replaced with exact text; this was a storage error, not invented supporting evidence.

The least certain decisions are **K3 correct at 007 and partial from 008**, **K6 correct from 004**, and **K7 correct from 029**. For K3, the complete geometry at 100 is followed by contradictory adopted plans at 125 and later. I count those sustained predictions as partial belief, rather than ignoring them as arithmetic noise; the exact boundary between belief and execution error is uncertain. For K6, I accept the accurate effect at the current solid marker as confirmation despite the absence of the right interface concept. For K7, “no OTHER plain items,” together with conserved held targets, is the win rule from the uncovered-target side. It is the leading belief despite listed alternatives. Ordinary orange crates were unseen, and the final file still entertains a different trigger time; I have not treated those open possibilities as adopted exclusions of the correct coverage rule.

K5 at 002 and 029 is also borderline in degree: the interpretations are poor, but marker switching or real blocked steps survive, so the rubric favors partial over wrong. This is a coarse seven-rule score; it should be read alongside the behavioral account, not as evidence that the player can execute every rule reliably.

Checkpoint headers supply the scored move counts. Thinking markers sometimes repeat or disagree slightly with the player's own numbered action recollections, so event numbers in the prose use the visible marker or an explicit approximate range. No claim of an exact experiment cost is made where those records do not support one.

All seven segment checks passed after the audit. Final run check: `run-H: 7 segments, 25 of 25 quotes found word for word, 0 problems`. The outputs are saved in [validation.txt](validation.txt).
