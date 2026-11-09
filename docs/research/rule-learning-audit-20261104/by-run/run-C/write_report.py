import json,hashlib,re,datetime,collections
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[4]
s=json.loads((O/'comparison-summary.json').read_text());rows=json.loads((O/'independent-labels.json').read_text(encoding='utf-8'));pts=json.loads((O/'curve-comparison.json').read_text());manifest=json.loads((O/'reading-manifest.json').read_text());ds=json.loads((O/'disagreements.json').read_text(encoding='utf-8'))
htmlpath=R/'docs/research/rule-learning-20261028/rule-learning.html';ht=htmlpath.read_text(encoding='utf-8');published=json.loads(re.search(r'const DATA=(.*?);const ONLY=',ht,re.S).group(1))['ps_modality-v1']['controller']
assert len(published['points'])==33 and all(p['score']==q['published_belief'] and p['actions']==q['actions'] for p,q in zip(published['points'],pts))
s['published_html_sha256']=hashlib.sha256(htmlpath.read_bytes()).hexdigest();s['published_html_all_33_points_match']=True
(O/'comparison-summary.json').write_text(json.dumps(s,indent=2),encoding='utf-8')

def cite(cp,rule,q=None,notebook=False):
 es=rows[cp]['labels'][rule]['notebook_evidence' if notebook else 'evidence']
 e=next((x for x in es if q and q in x['quote']),es[-1]);return f'cp{e["cp"]:03d}, line {e["line"]}: “{e["quote"]}” (`{e["path"]}`)'
report=f'''# run-C independent rule regrading — complete

33/33 checkpoints, cp000–032 across four segments; 8 rules each, **264/264 graded slots**, 0 unreviewed. All notebook and thinking text was read in order: {sum(x['lines'] for x in manifest):,} lines / {sum(x['characters'] for x in manifest):,} decoded characters in the supplied checkpoint files. Counts include repeated notebook text and headings. Per-checkpoint rationales and accumulated prior evidence are in `independent-labels.json`.

Independent labels were frozen at {json.loads((O/'freeze.json').read_text())['frozen_at_utc']}, before reading original labels or published curves. `labels.json` SHA-256: `{json.loads((O/'freeze.json').read_text())['files']['labels.json']}`. No originals, experiments, other runs, or global audit files were written. No subagents or gameplay were used.

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

- **M6 — clear over-credit:** original combined `correct` at cp007–009 and cp026–032 becomes `partial` (10 slots). Original notebook `correct` at cp026–032 likewise becomes `partial`; sources at cp007–009 change thinking→both because both support partial. The trace knows same-colour cases but never learns that grey↔black walking is legal while grey↔black pushing is forbidden. {cite(7,'M6',notebook=True)}. Later {cite(21,'M6','keep PUSHER')}. Source rules explicitly put white/grey together (`Nonblack`) and black separately. White/black reasoning alone is not the full M6.
- **M4 — clear scope/source errors:** cp028–030 combined correct→partial; cp028–032 notebook correct→partial; cp031–032 source thinking→both. The revised notebook describes specific edges and puts the all-boundaries idea under unconfirmed hypotheses. {cite(28,'M4','Player cannot')}. At cp010 source both→notebook: the new notebook rejects the old global rule and the thinking section is `(none)`. {cite(10,'M4','So region')}.
- **M4 — ambiguity:** notebook/source cp007–009 (3 slots), and combined/notebook cp026–027 (2 slots). The early notebook retains doubtful global wording but infers ACTION7 must matter; the late notebook has a local all-boundaries working assumption alongside an explicit non-universal rule. The independent grade preserves thinking knowledge at cp007–009 but gives notebook partial, and treats cp026–027 as incomplete global scope. {cite(26,'M4','Assume')}.
- **M2 — rubric issue:** cp002–032 combined and notebook correct→partial (31 slots, 62 fields). One-cell push is explicit, no-pull is implicit at best. Whether Sokoban vocabulary and push-only deadlock reasoning satisfy the no-pull clause requires a shared threshold; do not count these as clear original errors. {cite(2,'M2',notebook=True)}.
- **M3 — rubric issue:** cp002–032 notebook correct→partial, source both→thinking (31 slots, 62 fields). “destination free” might imply in-bounds; the independent reading requires the omitted bounds clause for notebook correct. Thinking retains explicit bounds refusal. {cite(2,'M3',notebook=True)}.
- **M3 — ambiguity:** cp000–001 combined partial→correct (2 slots). The trace explicitly rejects off-grid and box-on-box moves, but mistakes a blue goal for another box. Independent grading credits the generic collision belief, while original partial may penalize the object error. {cite(0,'M3','off-grid')}; {cite(0,'M3',"B's cell")}.
- **M7 — ambiguity:** cp002 notebook partial→correct and source thinking→both (1 slot). It is under Uncertain but says the plan assumes YES and uses that assumption. {cite(2,'M7',notebook=True)}. The rubric explicitly permits adopted working assumptions.
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
'''
(O/'REPORT.md').write_text(report,encoding='utf-8')
# Self-contained SVG chart, no server or external dependencies.
x=lambda a:48+a/226*600;y=lambda v:225-v*1.8
paths=[]
for field,color in [('published_belief','var(--chart-2,#e79450)'),('independent_belief','var(--chart-1,#66b2ff)')]:
 path=f'M{x(pts[0]["actions"]):.2f},{y(pts[0][field]):.2f}'
 for p in pts[1:]:path+=f' H{x(p["actions"]):.2f} V{y(p[field]):.2f}'
 paths.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3"/>')
grid=''.join(f'<line x1="48" x2="648" y1="{y(v)}" y2="{y(v)}" stroke="var(--border,#444)"/><text x="40" y="{y(v)+4}" text-anchor="end">{v}%</text>' for v in [0,25,50,75,100])
chart='<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;color:var(--foreground,#ddd);font:14px var(--font-sans,system-ui)}svg{width:100%;height:270px}text{fill:var(--muted-foreground,#aaa);font:12px system-ui}p{margin:8px 0}.legend{display:flex;gap:24px;flex-wrap:wrap}.pub{color:var(--chart-2,#e79450)}.ind{color:var(--chart-1,#66b2ff)}</style></head><body><div class="legend"><span class="pub">━ Published combined</span><span class="ind">━ Independent combined</span></div><svg viewBox="0 0 700 270" role="img" aria-label="run-C combined scores by game moves">'+grid+''.join(paths)+'<text x="48" y="246">0</text><text x="648" y="246" text-anchor="end">226 moves</text></svg><p>33 checkpoints · 264 rule slots · 0 unreviewed</p><p>Final: published 87.5%; independent 75%. Half the final gap is the disputed no-pull rubric threshold.</p></body></html>'
(O/'comparison.html').write_text(chart,encoding='utf-8')
(O/'progress.json').write_text(json.dumps(dict(completed=33,total=33,last_cp=32,frozen=True,comparison_complete=True,unreviewed=0,interpretive_disagreement_slots=70,validation_errors=0),indent=2),encoding='utf-8')
print('REPORT and chart saved; HTML publication verified; progress complete.')

