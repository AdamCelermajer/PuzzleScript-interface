# Run-A independent full-run audit

Complete: **24/24 checkpoints (000-023), 7 rules, 168/168 slots**, covering 744,387 input bytes. All notebook and thinking text was read sequentially, including empty checkpoint 005 and historical disk-error discussion. Labels, evidence, progress and current belief state were saved as each checkpoint was completed. There are **0 missing and 0 unreviewed slots**.

The full independent labels were frozen before accessing original labels, segment handoffs/start files, the identity key or published curves. [freeze.json](freeze.json) records the timestamp and hashes. Independent-label SHA-256:

`3b1e04f731fd26e00a6fbd8fb5076317fb197cbdd261f50d1bdcd24e15774abe`

All outputs are confined to this run-A directory. Original grades, published curves and live experiments were not changed. No subagents, model CLIs, gameplay, installs, restarts or API configuration were used. Source verification is static; it does not claim a historical runtime replay. Grader provenance was not researched again.

| Label | Combined | Notebook alone |
|---|---:|---:|
| correct | 0 | 0 |
| partial | 117 | 80 |
| wrong | 49 | 32 |
| absent | 2 | 56 |
| Total | 168 | 168 |

Sources: thinking 54, both 112, notebook-only 0, none 2. The two combined absences are K2 at cp000-001. Before cp008 no notebook exists. Final labels are partial for K1/K2/K3/K4/K6 and wrong for K5/K7. Partial labels capture directional movement, wall blocking, part of knight geometry, refusal effects and ACTION5 settlement. The player never learns movement-key landing selection and retains a clockwise-only jump model. At cp023, a promised notebook update is not present in the supplied checkpoint; the cp020 notebook remains current.

[Independent labels](independent-labels.json) and identical [standard labels](labels.json) contain every checkpoint/rule. [Evidence](evidence.json) gives exact checkpoint quotes and line numbers, prior-evidence chains, current-notebook references and thinking references. [Read log](read-log.json), [source verification](source-verification.json), [prefreeze decisions](prefreeze-decisions.md) and [final handoff](handoff.md) document scope and interpretation.

The post-freeze comparison uses this run's original four segment files and its entry in `curves-combined.json`. Run-A is controller-driven Knightoban. Its published corrected curve contains **no run-A correction overrides** and matches all **504 raw belief/notebook/source fields**. Differences below therefore apply equally to raw and published labels.

There are **108 differing fields across 56 checkpoint/rule slots**: 32 combined beliefs, 24 notebook labels and 52 sources. The other 112 slots match all three fields. These are disagreements, not 108 proven original errors.

| Classification | Differing fields | Affected slots | Scope |
|---|---:|---:|---|
| Clear error | 28 | 22 | K2 cp002-007 belief/source; cp008-023 source |
| Ambiguity | 17 | 9 | K7 cp002 belief; cp016-023 notebook/source |
| Rubric issue | 63 | 25 | K5 cp000-023; K7 cp000 belief |
| Total | 108 | 56 | Exact rows in disagreements files |

**Clear error:** At [cp002:1962](C:/Users/adamc/Desktop/syncall/uni/adam_project/PuzzleScript-interface/docs/research/rule-learning-20261028/grade/run-A/seg-1/cp-002.md:1962), the player states: "the player needs to be at (2,8) [border] to move left into (2,7). Not possible.". Original K2 remains absent through cp007 despite this explicit player-border restriction. The wall component earns partial under the compound K2 rule, even though orange-crate pushing is unknown. From cp008, earlier thinking plus the notebook supports source `both`, where originals say `notebook`.

**Rubric issue:** At [cp006:1145](C:/Users/adamc/Desktop/syncall/uni/adam_project/PuzzleScript-interface/docs/research/rule-learning-20261028/grade/run-A/seg-2/cp-006.md:1145), the player says: "The ring always goes clockwise, and the dashed shows the counterclockwise option." and immediately adds "So no hidden state there, just a ghost.". The frozen audit treats the animation account as wrong for choosing; the original grants partial for recognizing the alternate geometry. The rubric does not specify how much of a compound rule is substantial correct content. Before cp006, and in notebooks, absence versus a wrong animation explanation is also a scope judgment. Cp000 K7 similarly turns on whether reversed ball/hoop roles still earn partial for the intended overlap. Original partial is defensible in these cases; they are not asserted as clear errors.

**Ambiguity:** Cp002 K7 repeatedly adopts, rejects and conditionally reopens ring-on-ball. Late text explores a viable plan under interpretation B while retaining interpretation A. My frozen `wrong` is fragile; original `partial` is defensible, and suspension/absence is another possible reading. Full chronological quotations are in the `conditional_goal` group of [disagreements.json](disagreements.json). No frozen label was altered after this comparison. Cp016-023 notebook K7 says UNKNOWN and lists alternatives while continuing the H1 sweep and excluding ring-on-ball; whether this is an adopted working belief affects notebook/source, while combined `wrong` agrees.

**Unresolved adjudication: 80 field entries across 34 slots** (17 ambiguity + 63 rubric-issue fields). Every entry was reviewed and assigned a frozen label; unresolved means interpretive adjudication remains, not missing work. [unresolved.json](unresolved.json) lists every such field.

[disagreements.csv](disagreements.csv) and [disagreements.json](disagreements.json) contain every exact difference, classification, original location/note, and independent evidence. Original notes are reproduced as source material; they are not certified as literal quotations. [curve-comparison.csv](curve-comparison.csv) lists all 24 score points and exact half-credit totals. Combined scores differ at 20 points; notebook scores differ at 0, because the notebook disagreements exchange wrong and absent, both scored zero. Numerical differences alone do not settle the interpretive disagreements. [comparison-summary.json](comparison-summary.json) records all counts; [comparison-input-hashes.json](comparison-input-hashes.json) records read-only input hashes.

Validation passed: **24 checkpoint hashes, 168 slots, 271 exact evidence quote checks, 15 note checks, 121 persistence links**, plus 12 post-freeze comparison-group quote checks. Notes satisfy the 20-word limit. The unmodified repository checker returned `ok: 24 checkpoints x 7 rules`, with checkpoint discovery adapted to the inventory because this output spans four segments. Comparison checks cover all 504 fields and recompute all published score points. Frozen files and original input hashes remain unchanged.

From repository root, reproduce using the existing interpreter:

```powershell
.venv/Scripts/python.exe docs/research/rule-learning-audit-20261104/by-run/run-A/validate.py
.venv/Scripts/python.exe docs/research/rule-learning-audit-20261104/by-run/run-A/compare.py
```

These scripts write only this audit directory. See [validation.json](validation.json) and [comparison-validation.json](comparison-validation.json). This audit is complete; only the explicitly listed interpretation/rubric adjudications remain open.
