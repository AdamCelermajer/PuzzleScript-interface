# Run-F independent full-run audit

Complete: **32/32 checkpoints, 224/224 rule slots, all 4 segments**. Every checkpoint's entire notebook and thinking text was read sequentially, including repeated notebooks and long analysis. Labels and belief handoff were saved after each checkpoint. Zero unreviewed or ungraded slots. No subagents, model CLIs, gameplay, installations, source edits, or original-grade edits.

Independent labels were frozen before opening original labels, identity key, or published curves. Freeze time: 2026-11-04T18:06:38.896967+00:00. SHA-256 of `labels.json`:

`78ba25d7f401b6ee1bb896b1d29b604d52356943ab5758402efe435f4b123597`

## Counts

| Label | Combined | Notebook alone |
|---|---:|---:|
| correct | 84 | 79 |
| partial | 88 | 71 |
| wrong | 25 | 20 |
| absent | 27 | 54 |
| Total | 224 | 224 |

Evidence sources: both 167; thinking 30; none 27; notebook only 0. Every positive/wrong belief has precise checkpoint/line/section quotes. Persisted beliefs point to prior evidence and previous checkpoint. Absence rationales follow full reading, rather than keyword absence.

## Grounded findings

1. **Published correction overruns the first water observation.** `combine.py` corrects I5 to absent for cp0-7 inclusive. This is justified for cp0-6, whose dark pits are walls, but cp7 explicitly says **"the blue object at (3,4) is a blocker (stops the slide)."** See [cp7, line 173](../../../rule-learning-20261028/grade/run-F/seg-1/cp-007.md#L173). Later in the same checkpoint it calls this most likely a timing gate (line 1062). The independent grade is partial: the blocking effect is recognized, but a supposed passable phase is wrong. Whether this early gate interpretation merits correct or partial is debatable; absent is a clear error. The published source `none` is also wrong.
2. **The raw water grades conflate walls with water.** Raw I5 is correct at cp0-7 and notebook-correct at cp2-11. Independent I5 is absent at cp0-6, thinking-only partial at cp7-11, and partial in both from cp12. The published notebook correction matches the independent reading throughout cp2-11. The published combined correction only agrees through cp6.
3. **The no-chain belief is explicit and persistent.** Thinking at cp7 says "in sokoban you can't push two crates"; cp12's notebook states "Crate-vs-crate contact = no movement." The source explicitly propagates motion along crate chains (script lines 358/366/374/382). Independent I4 is wrong at cp7-31, agreeing with both original and published labels. This is a substantive learner error, not an additional grading disagreement.
4. **Water is mistaken for a timed gate.** The source animates six water sprites but every one blocks the player. Filling water removes a crate and creates walkable FilledWater. The trace learns disappearance and crossing but conditions them on a pre-existing passable gate phase. I5 and I6 remain partial after that discovery. These later labels agree with the published grades.
5. **Sliding-rule completeness drives most differences.** I2 is partial throughout independently; raw and published labels say correct throughout. The learner knows sliding to walls/blockers, but initially lacks water/crate applicability and later adopts incorrect water-phase applicability. This is classified as a rubric issue about how much of the composite I2 rule is essential, not 32 demonstrated original-grader errors.
6. **Four disputed belief-adoption slots differ from publication.** I3 cp5: partial versus absent (pushability is adopted as necessary, then questioned). I7 cp8, cp9, cp11: partial versus correct (feeding selected as an L4 objective while plant stopping retained for earlier levels). These are ambiguities. Cp10 returns to the plant account. From cp12 onward, the notebook explicitly states the generic stop-on-plant rule as fact; explicitly UNCONFIRMED alternative goals do not replace it, so I7 is correct. The pre-freeze decisions file also flags cp7/I4 and cp10/I7 as boundary cases, although those agree with publication.

## Exact comparison counts

A field disagreement is one of `belief`, `notebook`, or `source` at one rule/checkpoint. A slot is one rule/checkpoint, possibly containing several field disagreements. Notes are retained as context, not counted as categorical disagreements.

| Comparison target | Slots with differences | Belief fields | Notebook fields | Source fields | Total fields |
|---|---:|---:|---:|---:|---:|
| Original raw labels | 48 | 44 | 40 | 12 | 96 |
| Published corrected curves | 37 | 37 | 30 | 5 | 72 |

| Target | Clear-error fields | Ambiguity fields | Rubric-issue fields |
|---|---:|---:|---:|
| Raw | 25 | 9 | 62 |
| Published | 2 | 8 | 62 |

Published differences by rule/checkpoint, exhaustively:

- I2 cp0-31 combined: correct -> partial; cp2-31 notebook: correct -> partial (62 fields, rubric issue).
- I3 cp5: absent -> partial, source none -> thinking (2 fields, ambiguity).
- I5 cp7: absent -> partial, source none -> thinking (2 fields, clear error in absence/source; exact correct-versus-partial boundary remains interpretive).
- I7 cp8, cp9, cp11: correct -> partial, source both -> thinking (6 fields, ambiguity).

Raw differences add the wall/water conflation: I5 cp0-6 belief correct -> absent and source thinking/both -> none; cp2-11 notebook correct -> absent. At cp7 raw I5 correct -> partial is classified ambiguity and both -> thinking is a clear notebook-source error. The complete individual entries, original values, independent values, categories, rationales and precise evidence are in `comparison.json` and `disagreements.csv`.

**Unresolved adjudication:** no missing grades. Against publication, 36 assigned slots require interpretive adjudication (32 I2 rubric slots + 4 belief-adoption slots), representing 70 field differences. Against raw labels, 37 slots / 71 fields require adjudication. Category slot counts for raw are not additive: cp7/I5 has a clear source error and an ambiguous belief grade. Independently flagged boundary cases total 6 slots; two agree with publication.

## Curves and validation

Final independent combined and notebook scores are both **64.3%**, versus published **71.4%**. The final difference comes entirely from the I2 granularity choice. Of 32 published points, 30 combined-score points and 30 notebook-score points differ. At cp7, I5's +0.5 and I2's -0.5 cancel in the combined score: both curves show 57.1%, concealing the substantive label disagreement. Scores use correct=1, partial=0.5, wrong/absent=0, divided by seven, rounded to one decimal. `curve-comparison.csv` retains every checkpoint and exact rounded deltas.

Validation passed: 32 input checkpoint hashes, 224 exact rule-coverage entries, 363 exact quote references including line and section, valid grades/sources, notes on changes, and persistence links. The unchanged repository `grade/check.py` reported `ok: 32 checkpoints x 7 rules`, executed with the existing Python environment and an in-memory glob mapping to the inventoried source checkpoint paths (no source copies or edits). `validate.py` is reproducible from any working directory. Comparison additionally validates 274 quote references, original-input hashes, the frozen-label hash, and all frozen evidence-file hashes; all pass and originals remain unchanged.

Artifacts: `labels.json`, `freeze.json`, `independent-decisions.json`, `source-verification.md`, `progress.json`, `handoff.md`, `validation.json`, `comparison.json`, `disagreements.csv`, `curve-comparison.csv`, `comparison.html`, `validate.py`, `compare.py`, plus filtered `inventory.json` and `rules.json`. All are under this run-F folder. No provenance investigation was repeated.
