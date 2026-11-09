# Run-B independent full-run audit

Completed **29/29 checkpoints and 203/203 rule slots**, cp0-28, seven rules each. No unreviewed slots. Cp25-28 were read fully and graded strictly sequentially, saving each before reading the next. Cp24's entire source was reread to verify inherited state. Prior 175 judgments are unchanged; their original bytes are in `prior-000-024.json`. Earlier full reads are documented in the preserved batch notes, not claimed as newly repeated in this continuation.

Frozen before opening originals, identity key, corrected curves, or other audit grades at **2026-11-04T18:23:38.381152+00:00**. Independent-label SHA-256:

`54de80a1b6bcb4eeb28c94c040e6b3b77a12be82a315a78313d3fe0b4802986e`

Identity confirmed only after freezing: old IceCrates agent-driven run `20261021T144508-vast-fp8-harness2-153a4dc2/run-0002/rollouts/base1`.

## Coverage and validation

All 203 slots compared against both original raw segment labels and published `curves-combined.json`: 609 categorical fields per target. Raw and published run-B labels are identical; the published correction code changes run-F, not run-B. The older sparse `curves.json` notebook study is not a 203-slot comparator.

Independent combined counts: correct 108, partial 59, wrong 10, absent 26. All 29 checkpoint byte lengths/SHA-256 hashes match the inventory. Exact evidence quotes, <=20-word note excerpts, source locations, prior175 equality, preserved old artifact hashes, and frozen hashes validate. The unchanged repository rubric checker reports `ok: 29 checkpoints x 7 rules`, through virtual independent-label/rule/checkpoint routing with start.json disabled. No packages or services were needed.

Validation is structural and evidential; it does not certify every semantic judgment. One quote need not establish every component of a composite rule; explanations and full source windows provide context. `comparison.json` records all slots, not just differences.

## Exact differences

For EACH target (raw and published): **45 differing slots, 81 differing fields: 39 belief, 27 notebook, 15 source**. Classification: **51 rubric-issue fields, 28 ambiguity fields, 2 clear source-attribution errors in the independent audit**. These are not 81 demonstrated original-grader mistakes. No unambiguous original-label correction is established by this conservative adjudication; candidate corrections and reasonable original alternatives remain explicit.

Exhaustive differing checkpoint sets (B=belief, N=notebook, S=source):

- I1: B cp0; N cp0-1; S cp0-1.
- I2: B cp1-4,6-22,26-27; N cp2-23,26-28; S cp5,23,28.
- I3: B cp20-21.
- I4: B cp21.
- I5: B cp5-7,20-22,28; S cp20-22,28.
- I6: B cp15-17; S cp15-17.
- I7: B cp11,17; S cp11,18-19.

Every exact old/new value, evidence path/line/quote, raw JSON location, published location, classification, explanation and alternative is in `comparison.json`; `disagreements.csv` is the flat export.

## Evidence-based findings and alternatives

**I2 completeness is the main rubric issue (51 fields).** Independent grades require all essential stopping conditions, including water and immovable crates. Original labels credit core sliding while evaluating water separately under I5. Early notebook cp2:40 knows sliding until an obstacle but has not identified actual water. Cp13:126 explicitly permits blue-water vertical passage; cp26:34 repeats that error. Partial is justified under composite-rule completeness; correct is defensible if I2 measures core sliding. This is a calibration decision, not 51 clear grader errors.

**Initial controls are a belief-adoption ambiguity.** Cp0 Controls says ?Hypothesis: 4 = 4 directions? and mapping UNKNOWN; thinking says ?Probably?. Independent absent excludes tentative exploration. But the rubric explicitly accepts a single leading notebook hypothesis, so original correct is defensible. This also affects the unchanged notebook at cp1. Frozen absence is preserved, not retroactively rewritten.

**Water blocking has scope and replacement ambiguity.** Cp5:319 concludes the creature cannot pass in any state, supporting correct; partial can read its evidence as leftward-only. Cp20-22 L5 blocking may replace the old L4 exception or coexist with it. Cp24 appended general blocking and verified L6 predictions support all-correct despite stale earlier text. Cp26 explicitly reintroduces vertical passage. Cp27:1219-1227 retains it while adopting an opaque-blue solver simplification. Cp28:10 explains passage after gold conversion and :14 adopts opaque blue: frozen I2/I5 become thinking-correct, notebook-partial. Partial remains a reasonable alternative because the model is still called conservative. This boundary was disclosed before freeze.

**Gold passability may be learned earlier than the frozen audit credits.** Cp15:815 adopts horizontal exit, while :817 says ?probably both directions?. Frozen I6 remains partial through cp17; original correct accepts generalization from the observed exit. Neither should be presented as an indisputable mistake.

**Planning slips versus mechanical beliefs matter.** Cp20:1049-1051 and cp21:237-247 adopt separate approach/push predictions; cp21:217 predicts an incorrect trailing-box/player position after a chain. Frozen I3/I4 partial treats adopted predictions as beliefs; original correct can regard them as coordinate or implementation slips. Later cp22 corrections restore full mechanics independently.

**Goal exceptions are disputed, not erased by silence.** Cp11:687 calls the L4 plant a decoy; cp17:440 says the goal is something else. Frozen partial preserves earlier successful plant-stop knowledge plus a current-level exception. Original correct can regard the continuing hypothesis search as insufficient retraction. Cp18:216 explicitly rejects the plant goal, and both audits then agree on partial.

**Source attribution needs separate correction.** For cp18-19/I7, frozen `both` is inferior to original `thinking`: current notebook alone earns correct, while newer thinking produces partial. These are the two clear errors counted above, in the independent audit. `adjudication.json` also recommends thinking for cp17/I7 and cp20-21/I3, where both audits share `both`. These three shared cases do not inflate disagreement counts. A broad ?contributes some evidence? reading explains both, but the rubric's operational ?gives this label? reading favors thinking. No frozen file was edited.

## Game-source check

Post-freeze source verification: `puzzlescript_interface/games/ps_icecrates-v1/script.txt` defines all six water sprites together at 279 and `Obstacle = Wall or StillCrate or Water` at 291. Directional blocks at 356-386 implement persistent sliding, player pushes, chain propagation, absorption into FilledWater and stopping. Win condition 395 is `Some PlayerStill on Goal`. This supports the seven supplied rules and rejects real directional/rotor passability. The learner's ?water? tile6 is floor; its blue ?door? is actual water; gold27 is filled water. Source truth does not itself decide whether the learner had adopted a belief.

## Scores and limits

All 29 independently recomputed combined/notebook scores and published values are saved in `curve-comparison.csv`; published scores validate against its categorical labels. Final frozen combined score is 100.0%; notebook 85.7%. Published/raw final scores are both 92.9%. The final difference depends on I2 completeness and cp28's conservative-model interpretation; it is not a claim of indisputably perfect final understanding.

Preserved caveat: cp20 was judged before cp21, but its initial BOM-related save failed; it was saved after cp21 was read. Earlier notes state no cp21 evidence was used for cp20. Cp10's prior save-recovery disclosure also remains in the old batch notes. These prevent claiming a flawless save-before-read history for the entire run. Final cp25-28 did follow that order.

No subagents, model CLIs, gameplay, installs, services, commits, pushes, API setup, or edits outside this run-B audit folder. Originals, curves, other agents' files, shared reports and prior batch artifacts were preserved. Post-freeze adjudication is separate.

## Artifacts

- Frozen: `independent-labels.json`, `independent-handoff.md`, `freeze.json`, `batch-025-028.md`, `validation-final.json`.
- Comparison: `comparison.json`, `disagreements.csv`, `curve-comparison.csv`, `adjudication.json`, `validation-comparison.json`.
- Reproducibility: `validate-final.py`, `compare-final.py`; run from repository root with existing `.venv/Scripts/python.exe`. Previous batch scripts/artifacts remain intact.
