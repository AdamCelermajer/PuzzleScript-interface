# run-C independent rule regrading — complete

33/33 checkpoints, cp000–032 across four segments; 8 rules each, **264/264 graded slots**, 0 unreviewed. All notebook and thinking text was read in order: 9,168 lines / 845,445 decoded characters in the supplied checkpoint files. Counts include repeated notebook text and headings. Per-checkpoint rationales and accumulated prior evidence are in `independent-labels.json`.

Independent labels were frozen at 2026-11-04T18:09:58.171377+00:00, before reading original labels or published curves. `labels.json` SHA-256: `c1fc3816d281f55ef54df8c726dc6edb3bb68de00eeea138f49f366803d93cff`. No originals, experiments, other runs, or global audit files were written. No subagents or gameplay were used.

## Coverage and validation

- Independent combined grades: correct 138; partial 120; wrong 0; absent 6.
- Notebook-only grades: correct 97; partial 146; wrong 0; absent 21.
- All 33 × 8 checkpoint/rule pairs exactly match the run-C inventory.
- 1,304 evidence references (including repeated persistence references) pass exact quote, line, channel, and chronological checks. Every positive notebook grade has a citation to its effective notebook version.
- Supplied checker: `ok: 33 checkpoints x 8 rules`, using input copies under `validation-input/`.
- Frozen files and checkpoint input hashes verified; no validation errors or unreviewed entries remain.
- Absence is assigned only after full reading: combined M6/M7/M8 at cp000–001; notebook all rules cp000–001 and M6 cp002–006.

## Exact comparison

Original raw run-C grades and the published corrected `curves-combined.json` agree in **all 792 compared fields** (264 slots × belief/notebook/source). The published HTML also matches all 33 run-C curve points and its final labels. `combine.py` contains no run-C correction. Therefore the two comparisons below have identical results; do not add them together.

| Comparison against either original raw or published corrected | Count |
|---|---:|
| Slots with at least one differing field | 86 / 264 |
| Combined belief disagreements | 48 / 264 |
| Notebook-only disagreements | 80 / 264 |
| Source disagreements | 41 / 264 |
| Total differing fields | 169 / 792 |
| Clear-error slots / fields | 16 / 31 |
| Ambiguous slots / fields | 8 / 14 |
| Rubric-issue slots / fields | 62 / 124 |

**70 differing slots remain interpretive (8 ambiguity + 62 rubric issue).** They are completely reviewed and have frozen grades; they are not 70 unreviewed entries. The 16 clear-error slots are the auditor's evidence-backed judgments, not an assertion that every disagreement is objectively settled.

`disagreements.json` contains each target/cp/rule/field, exact old/new values, classification, explanation, original note, independent evidence and current notebook evidence. There are 338 records because raw and published targets each have 169 field differences. `disagreements.csv` is the compact equivalent.

## Findings by rule

- **M6 — clear over-credit:** original combined `correct` at cp007–009 and cp026–032 becomes `partial` (10 slots). Original notebook `correct` at cp026–032 likewise becomes `partial`; sources at cp007–009 change thinking→both because both support partial. The trace knows same-colour cases but never learns that grey↔black walking is legal while grey↔black pushing is forbidden. cp007, line 46: “Push box (4,2)up from (5,2): BLOCKED (player can't enter (4,2)B from (5,2)W). CONFIRMED T72.” (`docs/research/rule-learning-20261028/grade/run-C/seg-0/cp-007.md`). Later cp021, line 7: “keep PUSHER on same-color floors, let BOX cross boundaries.” (`docs/research/rule-learning-20261028/grade/run-C/seg-2/cp-021.md`). Source rules explicitly put white/grey together (`Nonblack`) and black separately. White/black reasoning alone is not the full M6.
- **M4 — clear scope/source errors:** cp028–030 combined correct→partial; cp028–032 notebook correct→partial; cp031–032 source thinking→both. The revised notebook describes specific edges and puts the all-boundaries idea under unconfirmed hypotheses. cp028, line 23: “Player cannot cross specific white<->black boundary EDGES: hidden per-level WALLS.” (`docs/research/rule-learning-20261028/grade/run-C/seg-2/cp-028.md`). At cp010 source both→notebook: the new notebook rejects the old global rule and the thinking section is `(none)`. cp010, line 49: “So region rule must be wrong/limited.” (`docs/research/rule-learning-20261028/grade/run-C/seg-1/cp-010.md`).
- **M4 — ambiguity:** notebook/source cp007–009 (3 slots), and combined/notebook cp026–027 (2 slots). The early notebook retains doubtful global wording but infers ACTION7 must matter; the late notebook has a local all-boundaries working assumption alongside an explicit non-universal rule. The independent grade preserves thinking knowledge at cp007–009 but gives notebook partial, and treats cp026–027 as incomplete global scope. cp026, line 76: “Assume all B-W edges walled except door” (`docs/research/rule-learning-20261028/grade/run-C/seg-2/cp-026.md`).
- **M2 — rubric issue:** cp002–032 combined and notebook correct→partial (31 slots, 62 fields). One-cell push is explicit, no-pull is implicit at best. Whether Sokoban vocabulary and push-only deadlock reasoning satisfy the no-pull clause requires a shared threshold; do not count these as clear original errors. cp002, line 13: “Pushing: walk into box; box moves 1 cell if destination free; else both blocked (observed).” (`docs/research/rule-learning-20261028/grade/run-C/seg-0/cp-002.md`).
- **M3 — rubric issue:** cp002–032 notebook correct→partial, source both→thinking (31 slots, 62 fields). “destination free” might imply in-bounds; the independent reading requires the omitted bounds clause for notebook correct. Thinking retains explicit bounds refusal. cp002, line 13: “Pushing: walk into box; box moves 1 cell if destination free; else both blocked (observed).” (`docs/research/rule-learning-20261028/grade/run-C/seg-0/cp-002.md`).
- **M3 — ambiguity:** cp000–001 combined partial→correct (2 slots). The trace explicitly rejects off-grid and box-on-box moves, but mistakes a blue goal for another box. Independent grading credits the generic collision belief, while original partial may penalize the object error. cp000, line 562: “If I push left, the box goes off-grid. So I can't push it left.” (`docs/research/rule-learning-20261028/grade/run-C/seg-0/cp-000.md`); cp000, line 1092: “push O up into B's cell? No, B is there.” (`docs/research/rule-learning-20261028/grade/run-C/seg-0/cp-000.md`).
- **M7 — ambiguity:** cp002 notebook partial→correct and source thinking→both (1 slot). It is under Uncertain but says the plan assumes YES and uses that assumption. cp002, line 43: “L2 plan assumes YES)” (`docs/research/rule-learning-20261028/grade/run-C/seg-0/cp-002.md`). The rubric explicitly permits adopted working assumptions.
- **M1, M5, M8:** no raw/published field differences. The independent methodology nevertheless records the ACTION7/action-button naming issue and the plural-objective interpretation for M8 so agreement is not mistaken for proof of an unambiguous rubric.

## Curve effect and interpretation

Every checkpoint's score is in `curve-comparison.csv` and `curve-comparison.json`; correct=1, partial=0.5, wrong/absent=0, divided by 8. Final independent combined score is **75.0%**, versus published **87.5%**; notebook-only is **68.75%**, versus published **93.8%** (93.75% before publication rounding). The combined final 12.5-point gap consists of M6's clear incomplete floor rule and M2's disputed no-pull threshold, 6.25 points each. It must not all be described as clear error. If only the clear M6 final combined over-credit is corrected, the original final combined score is 81.25%.

The independent combined score is 50% at cp000–001, 81.25% at cp002–009, and 75% at cp010–032. The cp010 decrease reflects the explicit adopted limitation of the global colour rule, not loss of evidence through silence. `comparison.html` plots frozen independent and published combined scores; it is a comparison artifact, not a replacement for the original publication.

## Artifacts

- `labels.json`: frozen rubric-format labels.
- `independent-labels.json`: full labels, evidence, notebook evidence, decision bases and checkpoint rationales.
- `freeze.json`, `reading-manifest.json`, `pre-freeze-review.json`, `methodology.md`: independence and source/interpretation record.
- `validation.json`, `validate.py`: coverage/quote/checker validation.
- `comparison-summary.json`, `disagreements.json`, `disagreements.csv`: complete counts and exact classified differences.
- `curve-comparison.json`, `curve-comparison.csv`, `comparison.html`: checkpoint score comparison.
- `current-belief-handoff.md`, `progress.json`: completed run state.

No provenance research was repeated. No original grades were changed. The unresolved work is human adjudication of the 70 interpretive disagreements if a single harmonized rubric is desired; the assigned full-run reading, grading, freeze, comparison, and validation are complete.
