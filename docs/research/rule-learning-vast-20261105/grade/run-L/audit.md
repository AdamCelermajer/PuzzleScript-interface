# Run L: final grading audit

The complete run passed `check_run.py` before the final semantic audit, after repairing two arrow-corrupted quotes. The audit then reconsidered every change into correct/wrong, the nine combined-label intervals longer than 100 moves, notebook recency, and the three restart markers. It included the predecessor's labels, which were the starting point rather than assumed ground truth. Relevant surrounding passages and the later conclusions in long windows were checked; occurrence of a quote alone was not treated as sufficient.

## Amendments

| Item | Change | Reason |
|---|---|---|
| cp-043 I3 | partial → correct; source thinking; notebook stays partial | The final adopted summary explicitly says automatic contact pushing. It also predicts the distant push from (9,10) into the crate at (3,10), finishing with player (2,10). The earlier route mistakes should not survive this explicit restoration. |
| cp-044 I3 | partial → correct; source thinking; notebook stays partial | Later thinking explicitly corrects the supposed pre-contact stop at (1,9): from (1,7), sliding right pushes the crate at (1,10), ending player (1,11). Remaining incorrect wall coordinates and inaccessible-route claims are insufficient to remove that restored belief. |
| cp-045 I3 | partial → correct; source thinking; notebook stays partial | It explicitly predicts pushing from (6,4), across (7,4), into crate (8,4), ending player (8,4) and crate (9,4). No final adopted contrary stop-before-contact plan replaces this. |
| cp-046 I3 | partial retained; new transition note | The final chosen plan explicitly says the slide from (3,12) stops at (3,10), moves no crates, and needs another left action to push crate (3,9). This is a rule error rather than just an unsuccessful route. |
| cp-029 I3; cp-052 I6 | repaired quotes | PowerShell had replaced arrow characters with question marks. Exact text is now copied from the checkpoints. |
| cp-002 I7; cp-055 I3 | stronger exact excerpts | The old route-heading and bare inability-to-stop excerpts were too indirect. The replacement quotes state the goal stop and the supposed exclusive adjacent push requirement. |
| cp-029 I7 | stronger exact excerpt | The old excerpt occurred after “maybe.” The replacement is the later selected “cleanest intended solution,” which adopts the goal-ending push plan. |

All segment start snapshots were refreshed, retaining each rule's most recent evidence note. The seg-10 and seg-11 handoffs were corrected. Requested sample scores, final labels, and first-correct checkpoints are unchanged. No predecessor belief label was changed.

## Decisions on disputed passages

* **cp-002 I7:** retained correct, with moderate confidence. The actual adopted five-move route crosses (2,4) during its early left slide, continues to (2,1), and only calls the later stop at (2,4) the goal. This is behaviourally specific belief evidence rather than credit merely for winning. The failed crossing at move 17 is the first especially explicit confirmation.
* **cp-007/008 I4:** retained partial because the code does not simply omit a general statement. After building an initially contiguous chain, it breaks when its moving front reaches another crate. The late cp-008 analysis also endorses that code as correct. This contradicts the supplied chain rule, so the single-case override does not require correct.
* **cp-008 and cp-029 I5:** retained wrong. The former continues using movable blue as a working solution model after identifying absorption; the latter selects pushing blue down as the cleanest intended solution. These go beyond merely asking whether blue is pushable. Later conditional tests in cp-060/061 do not independently create a new wrong label.
* **cp-017 versus cp-018 I7:** calling a layout a dud under the accepted stop condition is a planning/solvability conclusion, so cp-017 stays correct. cp-018 explicitly replaces that rule with pass-through or another state condition, earning wrong.
* **cp-025 I7:** retained wrong, with lower confidence. It revisits stop-on-goal and timing as competing “intended” conditions, while still acting on the premise that a different condition is needed and pursuing undo/count tests. It has not clearly adopted stopping again. cp-027's viable stopping plan is the clear restoration. A reader who interprets the cp-025 disjunction as retracting the earlier categorical rejection could reasonably prefer another label here.
* **cp-043–046 I3:** amended as above. Map errors and absence of a found route do not automatically establish a wrong pushing rule. An explicitly predicted pre-contact stop or an exclusive adjacent-start requirement does.
* **cp-044 I6:** retained correct. An early two-stage push-before-water account is superseded later by a direct push of crate (3,9) into blue (3,6), destroying the crate and opening the row. The adopted erroneous post-absorption stop appears clearly in cp-046 instead.
* **cp-055 I3:** retained partial. Beyond merely saying (3,5) is unreachable, it says the ONLY way to push down from crate (4,5) is from (3,5), while recognising (2,5) is reachable. This is a substantive contact-rule restriction. cp-056 explicitly retracts it.
* **cp-059/060 I3:** retained correct. The current full solver explicitly checks for and pushes crates reached inside the sliding loop. The cp-060 short note about the inaccessible adjacent square is ambiguous and embedded in a genuinely blocked current geometry; it does not explicitly replace that operational model. cp-061 again predicts a distant push. The later cp-062 categorical restrictions do earn partial.
* **cp-056/057 I4:** correct is brief, supported by explicit recognition of the observed 359/378 chain pushes, including the encounter with separated crates. The following continuation loses this plan and the updated notebook returns to blocker-based code. Correct is not carried merely because it once appeared.
* **Final I3/I4:** single-crate contact pushing and following are correct. The contiguous-chain description has an incorrect newly encountered crate barrier and imprecise “behind the lead crate” wording. Those defects keep I4 partial. Open uncertainty about multiple water cells in one push is not a contradictory belief and does not reduce I6.

## Labels held longer than 100 moves

Intervals below run from the first checkpoint with the label to the next different label, or the end. Repeated checkpoint moves do not imply additional actions. All nine intervals were reviewed against intermediate text, not just the boundary quotes.

| Rule and label | Checkpoints holding it | Move interval | Review |
|---|---|---|---|
| I1 correct | 000–037 | 1 to 322 | Standard mapping in the early notebook and later restatements, including restart continuations; the first adopted replacement is the quadrant claim at cp-038. |
| I1 correct | 040–068 | 325 to 437 | Explicit standard-mapping restoration, subsequent predicted directional moves, and final controls agree. Imagined row lengths and mistaken player positions are state errors. |
| I2 correct | 000–068 | 1 to 437 | Wall/border sliding persists throughout. Water and crate exceptions are evaluated under I5/I3/I4; their errors do not erase the substantial ordinary sliding rule. |
| I3 correct | 005–020 | 29 to 171 | Distant push at 28, subsequent adopted push/follow code and routes, and pair pushes support it. Passing alternative models do not erase it. cp-021 newly saves an explicit pre-crate stopping action and second-action push. |
| I4 partial | 007–049 | 44 to 354 | Initially contiguous groups are understood and used. The saved implementation explicitly blocks newly encountered crates; later plans do not clearly remove that restriction. At cp-050 even the adjacent pair is declared unable to move, causing wrong. |
| I5 correct | 034–068 | 268 to 437 | Blocking at 267, later explicit always-solid-until-filled descriptions, and final world model support it. Colour/timer questions and proposed pushability experiments remain alternatives. The direct blocked test at 404 is consistent. |
| I6 correct | 019–045 | 150 to 334 | Filled-arm account at 150, the single-sacrifice fifth-level plan, continued sliding through gold, and later direct-absorption descriptions sustain it. cp-044's temporary two-stage account is replaced; cp-046 adopts a false stopping position after absorption. |
| I7 correct | 002–017 | 12 to 125 | Adopted second-level route, failed crossing at 17, and explicit stop requirement at 107 support it. cp-017 calls the layout unsolvable under that rule; cp-018 changes the rule itself. |
| I7 wrong | 018–026 | 125 to 243 | Repeated selected count/timing/pass-through accounts, including cp-020's explicit rejection of stopping. cp-025 is the main ambiguity noted above. cp-027 supplies a new feasible stop-on-goal plan and explicitly restores the rule. |

## Transition ledger

The following ledger lists every final transition into correct or wrong, including the initial correct entries. Each was checked against surrounding text and later material in its window. Additional notes above explain why particular excerpts are adopted beliefs and whether later corrections supersede them. Quotes retain their notebook/thinking prefixes.

| Checkpoint | Move | Rule | Change | Evidence |
|---|---:|---|---|---|
| cp-000 | 1 | I1 | initial -> correct | T: ACTION1..4 = up/down/left/right |
| cp-000 | 1 | I2 | initial -> correct | N: Sliding ice puzzle: move in a direction, slide until hitting wall/border, stop before it. |
| cp-002 | 12 | I7 | partial -> correct | T: stop at (2,4) = goal. |
| cp-003 | 13 | I3 | absent -> wrong | N: 21 = wooden crate (brown, also wall). |
| cp-005 | 29 | I3 | wrong -> correct | N: player ends directly BEHIND crate final pos. |
| cp-007 | 44 | I5 | absent -> wrong | N: movables={22:[(3,4)], 21:[(5,4),(5,5),(5,6)]} |
| cp-007 | 44 | I6 | absent -> wrong | N: posmap={cell:(cell[0]+dist*dr, cell[1]+dist*dc) for cell in chain} |
| cp-008 | 48 | I6 | wrong -> correct | T: The gold at (3,4) is passable (the player can slide through). |
| cp-011 | 54 | I5 | wrong -> correct | T: Accept: the wave is a permanent wall to the player. |
| cp-016 | 107 | I5 | correct -> wrong | T: The player passes through blue tiles |
| cp-018 | 125 | I7 | correct -> wrong | T: The win must be a pass-through or state condition. |
| cp-019 | 150 | I5 | wrong -> correct | T: each arm is solid until its own crate is absorbed |
| cp-019 | 150 | I6 | partial -> correct | T: each arm is solid until its own crate is absorbed, and after that it becomes passable. |
| cp-023 | 184 | I3 | partial -> correct | N: player PUSHES crate A instead of stopping before it |
| cp-027 | 243 | I7 | wrong -> correct | T: But "stop on the goal" is the primary victory condition |
| cp-028 | 244 | I7 | correct -> wrong | T: the win condition here must be something else. |
| cp-029 | 244 | I5 | correct -> wrong | T: the cleanest intended solution: push the blue (5,5) down |
| cp-029 | 244 | I7 | wrong -> correct | T: the cleanest intended solution: push the blue (5,5) down → it ends at (10,5), the player at (9,5) = goal. |
| cp-031 | 247 | I7 | correct -> wrong | T: So the win is not the player on the goal at the end of the action. |
| cp-034 | 268 | I5 | wrong -> correct | N: at 24 solid (blocked col5 slide at (6,5)). |
| cp-037 | 316 | I3 | partial -> correct | T: Crates (21) are pushed automatically on contact and slide to the end of the line. |
| cp-037 | 316 | I7 | wrong -> correct | N: L1-L3 won by LANDING on goal. |
| cp-038 | 322 | I1 | correct -> wrong | T: the quadrant hypothesis is confirmed |
| cp-040 | 325 | I1 | wrong -> correct | T: A1=up, A2=down, A3=left, A4=right. |
| cp-043 | 331 | I3 | partial -> correct | T: automatic push on contact (object slides to line end, player ends directly behind it) |
| cp-045 | 333 | I7 | correct -> wrong | T: So the player can't reach (9,5). So the win isn't "player ends on the goal." |
| cp-046 | 334 | I7 | wrong -> correct | T: Let me reconsider the goal (9,5). The player needs to end on (9,5). |
| cp-047 | 347 | I6 | partial -> correct | T: the player CONTINUES sliding (because the path is now clear). |
| cp-050 | 354 | I4 | partial -> wrong | T: So the crates (3,9) and (3,10) are stuck (they block each other). |
| cp-053 | 360 | I6 | partial -> correct | T: Player continues: (3,5), (3,4), (3,3), (3,2)=7 wall. Player stops at (3,3). |
| cp-054 | 375 | I3 | partial -> correct | T: up column 12 - this will push the crate up to (3,12). |
| cp-055 | 392 | I4 | partial -> wrong | T: Push left: blocked by (3,9). Stop at (3,11). |
| cp-056 | 393 | I3 | partial -> correct | T: player can start at (2,5); no need to stop at (3,5). |
| cp-056 | 393 | I4 | wrong -> correct | T: Chain push: crates can push other crates; observed f359/f378. |
| cp-059 | 395 | I3 | partial -> correct | N: res=push_crate(nr,nc,d,crates,blue_pass) |
| cp-061 | 400 | I7 | correct -> wrong | T: So the player can't stop on the goal. So the win must be a pass-through or a transformation-timing. |
| cp-062 | 404 | I4 | partial -> wrong | T: Crate B is blocked by crate A (4,3). So crate B doesn't move |
| cp-063 | 404 | I3 | partial -> correct | T: In the actual game, the player pushes the crate when it reaches it during a slide. |
| cp-063 | 404 | I6 | partial -> correct | T: If the lead hits a shatter, the crate is removed, and the group continues. |
| cp-064 | 405 | I7 | wrong -> correct | N: 32 A2  -> P(9,5)  [crate 4,5 -> 10,5; PLAYER ON GOAL = WIN] |
