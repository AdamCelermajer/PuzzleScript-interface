# Independent full-run audit: run-D

Completed all 25 checkpoints (cp000-cp024), all notebook versions and all thinking, in sequence: **175/175 rule slots**. No unreviewed or unassigned entries. No gameplay, subagents, model CLIs, installations, or changes to original experiment/grading files.

Independent labels were frozen before reading original grades, identity, handoffs, or curves. SHA-256: `6cef23513f3801a82bf12d04cfdd2fc6289951e49bea0567df59f61d69211e6d`. The manifest also freezes evidence, reading coverage, source verification, rules, handoff, and pre-comparison ambiguity notes. The progress log preserves checkpoint saves and pre-freeze refinements.

## Counts and coverage

| Labels | Correct | Partial | Wrong | Absent | Total |
|---|---:|---:|---:|---:|---:|
| Independent combined | 95 | 64 | 0 | 16 | 175 |
| Independent notebook only | 77 | 34 | 0 | 64 | 175 |
| Original raw combined | 93 | 66 | 0 | 16 | 175 |
| Published corrected combined | 93 | 66 | 0 | 16 | 175 |

Sources: 95 both, 64 thinking, 0 notebook-only, 16 none. All absence judgments followed full reading. Quote locations and prior checkpoint links are in `evidence.json`; omission from a later notebook never erased a carried combined belief.

## Exact disagreements

The independent audit agrees on **173/175 combined labels**, **175/175 notebook labels**, and **175/175 source labels** with each comparator. That is 523/525 matching categorical fields. Notes are evidence prose, not additional categorical fields. The raw and published corrected run-D series match all 525 fields, with no run-D publication corrections.

| Checkpoint | Rule / field | Frozen independent | Raw original | Published corrected | Assessment |
|---|---|---|---|---|---|
| 011 | K4 / belief | correct | partial | partial | ambiguity |
| 012 | K4 / belief | correct | partial | partial | ambiguity |

These are **two unique disagreements**, appearing against two comparators; they are not four independent disputed slots. Categories: 0 established clear errors, 2 ambiguities, 0 rubric-issue disagreements. Both remain unresolved semantic adjudications; every slot nevertheless has a frozen assigned grade.

At cp011 the player adopts dynamic suppression: “an endpoint is suppressed if a bright ring or cage currently occupies that tile.” It also accepts brick centers and excludes wall/player landing cells. The frozen audit credits this essential landing model, and cp012 carries it forward. The competing partial grade is defensible because the text never clearly states restoration/cancellation when neither endpoint is free, and earlier endpoint-in-range constraints are not clearly retracted. After freezing, the original seg-1 handoff confirmed that its grader explicitly retained partial for refusal-rule incompleteness. This audit does **not** establish that the original grader was wrong at these two points.

At cp011 and cp012 the weighted score is 85.7% in the frozen audit versus 78.6% raw/published, a 7.1 percentage-point difference after rounding. Every other checkpoint score matches; all notebook scores match. Final combined and notebook scores are 78.6% in all three series. `curve-comparison.csv` contains all 25 exact aligned rows and counters.

## Grounded findings

- Controls, frozen dark/dashed selection, and ACTION5 placement/release are adopted by cp001. General jump geometry is adopted by cp004. Notebook-only grades remain tied to the cp001 text through cp019; the notebook catches up at cp020.
- K2 remains partial: wall blocking is learned, but no orange normal-crate pushing belief appears anywhere in the fully read run.
- K7 remains partial: the player adopts “all rings caged.” Source line 154 requires every target covered; line 97 includes both red and normal crates. The observed equal ring/target levels do not establish the complete source rule. K2 and K7 are shared rubric-scope limitations, not original-versus-audit disagreements.
- K4 is partial from cp013 onward: cp013 explicitly requires both endpoints in range. In cp024 its proposed simulator removes the ring, assigns no dark endpoint when neither is valid, then freezes the player. Source lines 129-133 instead generate each available landing independently and cancel when none exists. This supports the original final partial grade.
- The final notebook and combined grades are K1 correct, K2 partial, K3 correct, K4 partial, K5 correct, K6 correct, K7 partial; all final sources are both.

The pre-freeze ambiguity registry flags 8 slots across three interpretive questions. Six agree with the originals (K4 cp003-004; K3 cp021-024). The two remaining slots are the K4 cp011-012 disagreements above. These flags are not unread entries or pending coverage work.

## Validation and limitations

`validate_independent.py` passed: exact inventory/rule coverage, all 25 checkpoint hashes, 409 verbatim quote references with section/line checks, valid grades/sources, required change notes, source-rule excerpts, and frozen hashes. The repository's unchanged `grade/check.py` also returned `ok: 25 checkpoints x 7 rules`; a discovery-only adapter supplied the existing checkpoint paths so no source checkpoints needed copying. Existing local Python was used, with no install.

`source-verification.json` records independent static review of the local Knightoban source. This is not new gameplay or an independent historical-source-version reconstruction. Prior provenance work was not repeated. Literal quote validation cannot resolve semantic rubric ambiguities.

All outputs are under this `by-run/run-D/` directory. Main deliverables: `independent-labels.json` (identical `labels.json` convenience copy), `evidence.json`, `comparison.json`, `curve-comparison.csv`, `freeze-manifest.json`, `validation.json`, `reading-coverage.json`, `source-verification.json`, `independent-progress.md`, and `handoff.md`. Original labels, prior partial audit files outside this directory, published curves, and live experiments remain untouched.
