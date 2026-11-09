import runpy,pathlib
globals().update(runpy.run_path(str(pathlib.Path(__file__).with_name('final-compare.py'))))
# Verify every supplemental comparison excerpt against its precise source line.
extra=0
for row in allrows:
 for e in row['current_notebook']['selected_exact_lines']:
  assert texts[e['cp']].splitlines()[e['line']-1]==e['quote'];extra+=1
v=read(O/'comparison-validation.json');v['supplemental_exact_line_checks']=extra;write('comparison-validation.json',v)
report=f'''# Run-E independent audit completed

65/65 checkpoints, 520/520 rule slots. This continuation added cp60–64 (40 slots), read all their notebook and thinking text, and preserved the prior 480 judgments. No combined, notebook, or source grade changed in the final five checkpoints. All original artifacts remain untouched; prior own versions are preserved in before-60 snapshots.

Independent freeze: {f['frozen_at_utc']}; SHA-256 `{f['files']['frozen-independent-labels.json']}`. The freeze preceded opening original segment labels, identity key or curves. `frozen-independent-labels.json` and `independent-labels.json` remain identical and unchanged after comparison. Interpretive cautions are separate in `post-comparison-adjudication.json`.

## Coverage and comparison

Both comparison baselines cover exactly cp0–64 and M1–M8: 520 slots and 1,560 belief/notebook/source fields each. The raw segment labels and published `curves-combined.json` are identical for run-E; its `corrected` maps are empty. The README's suggested M5 absent interpretation was not applied to the published run-E JSON. `curves.json` is the earlier sampled notebook-only series, not a 65-checkpoint baseline; it is not stretched into invented checkpoints.

187 slots differ on at least one field: 155 belief, 154 notebook, 60 source differences (369 field differences). These are the same against both baselines. Classifications comprise 82 clear-error field differences, 211 ambiguities, and 76 rubric issues. These counts include repeated persistence windows and coupled source changes, not 82 independent discoveries or a measured grader error rate.

`comparison-all-520.json` records every agreement and disagreement; `differences.json` records each differing slot, exact old/new field values, raw JSON locations, published locations, independent quotes, current-notebook origin/line ranges, selected exact notebook lines, rationale, classification and alternatives. `comparison-summary.json` groups precise checkpoint lists by rule/field/value/classification.

## Grounded findings

- **M1, controls:** raw/published correct versus independent partial at cp2–64; notebook differs at cp3–64. Cp5 notebook line22 says `ACTION5/ACTION6: "not available" (exist but context-locked; never seen available).` That adopted context-lock explanation contradicts treating the complete no-action-button clause as established. Cp5–32 are classified clear over-credit under the compound rule. Elsewhere this is a rubric issue: later unavailability may be enough operationally, even without an explicit universal statement. Four directions are consistently known.
- **M5, grey passage:** partial in the independent audit from cp2 onward versus absent through cp31 and wrong thereafter. Cp5 notebook line35 lists `(1,1)-(1,2),(1,2)-(1,3)` as open; its map identifies (1,2) as checker, with white and dark neighbors. Cp33 line13 calls checker `decoration, no effect`. Local passage knowledge supports partial, but the bridge principle was never adopted. Absent (no general rule) and wrong (denial of special function) remain alternatives. This entire family is ambiguity, not a blanket error finding.
- **M7, crate destinations:** cp9 thinking line76 identifies the moved crate as `box on white`. At cp14 line21 it also concludes `the box can't cross the dark tile`; correct cases coexist with a false restriction. Raw wrong at cp14–20 loses substantial correct cases. At cp21 the original note quotes retraction of an always-blocked dark-to-blue edge, replacing it with per-edge walls; raw absent through cp29 wrongly erases retained cross-colour movement knowledge under persistence. Partial is supported, with a stricter alternative explicitly recorded. Earlier cp9–13 observation-versus-belief disputes remain ambiguous.
- **M3, collision notebook/source:** cp5 notebook line15 explicitly says `blocked if box would go off-grid or into wall/box`; combined correct persists. Later notebooks omit crate-crate blocking. Raw absent for many later notebooks may miss implied boundary deadlocks (ambiguity); cp58 explicitly includes on-board requirements, making absent a clearer omission. Raw correct at cp57/59–64 depends on reading generic `free` as crate-crate blocking despite the detailed single-box algorithm and multi-box uncertainty; classified ambiguity. Frozen `thinking` source is itself imperfect where the decisive full collision evidence is an older notebook. This provenance/rubric issue is disclosed separately, not silently adjudicated into the frozen labels.
- **M4/M6 early effects:** cp2 thinking line289 says `right from (0,1) failed.` Cp7 line104 says `Pushing the box down from (0,2) failed!` The audit gives partial under the rubric's right-effect/wrong-cause clause; originals give absent for M4 cp2 and M6 cp7–13. Whether these coordinate-specific observations constitute adopted floor-rule fragments remains ambiguous.

## Final evidence

Cp60–62 retain explicit push-only behavior, automatic box-on-target completion, and invisible walls shared by player/crate. Cp63's entire 1,514-line thinking window proposes and debugs a solver using those walls. It explicitly accepts `Given that in the actual game, blocked pushes were box-forward walls` (exact location in the frozen M6 citation), while revising uncertainty about one bridge and a claimed unsolvability proof. Cp64 continues replica debugging. None adopts the actual white/black restriction, general grey bridge, push colour compatibility, or unrestricted crate destinations.

Final combined labels: M2/M3/M8 correct; M1/M4/M5/M6/M7 partial. Final notebook differs only on M3 (partial). This is not evidence that the agent learned the general hidden colour rules: the partial labels credit particular observed cases with mistaken causal accounts.

## Validation and limitations

`final-validation.json` validates all 65 input byte counts/SHA-256 hashes, all non-absent primary and supporting evidence quotes/line locations and N/T sections, note lengths/exact text, prior 480-record equality, and preservation of prior own output artifacts. Repository checker: `ok: 65 checkpoints x 8 rules`. `comparison-validation.json` records comparison input/output hashes, {extra} supplemental exact-line checks, full baseline coverage and unchanged freeze hashes. No validation errors remain.

Cp0–59 full-read attestations are inherited from the authorized earlier audit; this continuation independently read cp60–64 in full and validated the whole retained dataset, rather than re-reading every earlier thinking window. Cp61 was displayed after cp60 was judged but before cp60's save succeeded because the Python alias was absent; cp60 was then saved using the existing virtualenv before cp61 was graded. The existing save helper used the Windows default encoding when loading JSON: validation detected corrupted serialized quote text. The exact prior UTF-8 snapshot was restored and final records reconstructed before freezing; prior labels now compare exactly. No installs or original edits were used.

Classifications are evidence-based interpretive judgments, not a second independent ground truth. Original evidence notes can be paraphrases; they are retained as original notes, not falsely certified as exact quotes. Exact-text certification applies to the independent and supplemental source excerpts. No gameplay was run, so local map assertions and replica outcomes are assessed as beliefs, not verified game facts. All work was performed directly, without subagents or model CLIs.
'''
(O/'FINAL-REPORT.md').write_text(report,encoding='utf-8')
(O/'README.md').write_text('Run-E audit COMPLETE: 65 checkpoints / 520 slots, independently frozen before comparison.\nSee FINAL-REPORT.md, freeze.json, final-validation.json, comparison-all-520.json, differences.json, comparison-summary.json and comparison-validation.json.\nEarlier progress outputs are preserved in before-60 snapshots.\n',encoding='utf-8')
(O/'current-belief-handoff.md').write_text('Completed cp64; all 65 checkpoints and 520 judgments frozen before comparison.\nCombined: M2/M3/M8 correct; M1/M4/M5/M6/M7 partial.\nNotebook: same except M3 partial.\nHidden-wall explanations persist through final solver/replica debugging; push-only explicit.\nNo general colour mechanics adopted.\nOriginal raw and published run-E fields identical; see FINAL-REPORT.md for differences and alternatives.\nFrozen labels unchanged; adjudication concerns separate.\n',encoding='utf-8')
write('completion-manifest.json',dict(completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files={n:sha(O/n) for n in ['FINAL-REPORT.md','frozen-independent-labels.json','independent-labels.json','freeze.json','final-validation.json','comparison-all-520.json','differences.json','comparison-summary.json','comparison-validation.json','post-comparison-adjudication.json','progress.json']}))
print('Report and completion manifest saved; supplemental source checks',extra)

