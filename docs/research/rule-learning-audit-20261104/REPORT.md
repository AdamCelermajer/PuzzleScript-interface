# Partial independent audit — incomplete

The requested full regrade was **not completed**. This directory must not be used as a replacement grade set or to redraw curves.

## Coverage

- Inventoried and hashed all 208 checkpoints and 1,554 rule slots across A–F (6,641,149 bytes).
- Fully read and independently labelled only checkpoint 000 of runs B, D and E: **3/208 checkpoints, 22/1,554 labels**.
- **205 checkpoints / 1,532 labels remain unreviewed.** Evidence files are accessible; these are unreviewed, not evidence-missing or absent beliefs. No invented labels fill these slots.
- Grader for these 22 labels: this session's gpt-6-astra, high reasoning effort. No additional model, gameplay, API grading application, package installation or service operation was used.
- Original rubric and rule IDs preserved. Initial checkpoints have no preceding belief state. Full sequential grading of each run remains necessary.

## Verified historical grader provenance

Direct local Claude JSONL records associate all **29/29 segment assignments** with assistant message model **`claude-opus-5-5`**. No Haiku model appears in those segment records. `provenance.json` records each absolute log path, assignment, model-message count and an exact line reference with timestamp. This supports the README's Opus 5.5 attribution for the combined study, rather than the recollection of Haiku.

Scope: this verifies locally recorded model metadata, not independent provider-side execution attestation. Assignment/model fields were extracted programmatically; grading message bodies were not displayed. Earlier notebook-only grading was not investigated.

## Independence and comparison

The required README read disclosed the existing 23-label spot check and its reported errors before grading. This is a known limitation on blindness. Prior raw `labels.json`, `start.json`, grader handoffs, combined curves and the identity key have **not** been opened for grading. The key remains unread. The independent labels were saved and hashed before any comparison; **no comparison has been performed**, because the requested independent regrade is incomplete. `disagreements.json` uses null items and `not_compared`, not an empty list implying agreement.

## Findings established so far

- **Clear grading errors:** none independently established; no original-label comparison yet. The README's three reported errors are not new audit findings.
- **Ambiguity:** B/000/I1 earns correct here under the rubric's explicit allowance for a single leading notebook hypothesis. Notebook: “Hypothesis: 4 = 4 directions, 1 = other verb (interact/jump/toggle).” Thinking: “Probably: move up/down/left/right, and one other action (interact/jump?).” Exact action mapping is not required by I1. A stricter reading of the unconfirmed-hypothesis context could make this absent; retain this as a belief-threshold ambiguity, not a clear correction. Other 21 labels are absent after full checkpoint reads.
- **Rubric/documentation issue:** README says beliefs persist until contradicted or “drops it”; INSTRUCTIONS explicitly says omission from a notebook rewrite does not remove a belief. The latter is the operative rubric. Omission alone must not reduce a combined label in future grading.
- **Source qualification:** current source supports the 22 rule definitions, with evidence lines in `source-review.json`. IceCrates I3's stop-next-to-crate description is the ordinary blocking case: water consumes the crate (I6), so that wording must not be applied universally to water. No method parameters or rule definitions were changed.

## Validation and limitations

`validate.py` checks checkpoint hashes, graded-rule coverage, quote existence/offset/line/20-word limit, current source quote lines and source hashes, and complete segment coverage in the provenance extraction. Absence is supported by a full checkpoint read, not a fabricated quotation. See `validation.json` for actual results. Static source inspection did not validate historical game-source revisions or run the game engine.

The incomplete coverage is an execution limitation, not an inaccessible-evidence finding. Remaining work is the full sequential reading and grading, then a frozen-label comparison against both raw and corrected published labels, followed by evidence-based disagreement classification. Original grades and curves were not changed.
