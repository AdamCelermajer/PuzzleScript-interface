"""Post-freeze comparison of run-D only. Does not modify any frozen input."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
BASE=ROOT/'docs/research/rule-learning-20261028'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
freeze=read(OUT/'freeze-manifest.json')
for name,digest in freeze['sha256'].items():assert sha(OUT/name)==digest
ind=read(OUT/'independent-labels.json')
ev={(x['cp'],x['rule']):x for x in read(OUT/'evidence.json')}
raw=[]; inputs={}
for s in range(3):
    p=BASE/f'grade/run-D/seg-{s}/labels.json'
    inputs[str(p.relative_to(ROOT)).replace('\\','/')]=sha(p)
    raw.extend(read(p))
assert [x['cp'] for x in raw]==list(range(25))
identity=read(BASE/'grade/key.json')['D']
meta=read(BASE/'grade/run-D/meta.json')
assert identity['run']==meta['run'] and identity['game']=='ps_knightoban-v1'
pub=read(BASE/'curves-combined.json')[identity['run']]
assert pub['blind_id']=='D'
assert [x['cp'] for x in pub['checkpoints']]==list(range(25))
for rel in ['curves-combined.json','grade/key.json','grade/run-D/meta.json','combine.py','grade/run-D/seg-1/handoff.md']:
    inputs[str((BASE/rel).relative_to(ROOT)).replace('\\','/')]=sha(BASE/rel)
published=[{'cp':x['cp'],'labels':{r:{k:x[k][r] for k in ('belief','notebook','source')} for r in x['belief']}} for x in pub['checkpoints']]
assert all(a['labels'][r][k]==b['labels'][r][k] for a,b in zip(raw,published) for r in a['labels'] for k in ('belief','notebook','source'))
assert all(not x.get('corrected') for x in pub['checkpoints'])

reason=('Frozen independent grade credits the adopted empty-endpoint model after brick-center and dynamic occupancy corrections. '
        'Original partial is defensible: no explicit no-free-end cancellation/player restoration, and prior endpoint-in-range constraints '
        'were not clearly retracted. This is an essential-content/persistence boundary, not a demonstrated original grading error. '
        'The original seg-1 handoff, read only after freezing, explicitly gives the missing/refused-move rationale.')
diffs=[]
summaries={}
for name,other in [('original_raw',raw),('published_corrected',published)]:
    counts=Counter();slots=set()
    for a,b in zip(ind,other):
        assert a['cp']==b['cp'] and set(a['labels'])==set(b['labels'])
        for r,v in a['labels'].items():
            for field in ('belief','notebook','source'):
                if v[field]!=b['labels'][r][field]:
                    assert (a['cp'],r,field) in [(11,'K4','belief'),(12,'K4','belief')]
                    counts[field]+=1;slots.add((a['cp'],r))
                    diffs.append(dict(comparator=name,cp=a['cp'],rule=r,field=field,
                        independent=v[field],original=b['labels'][r][field],category='ambiguity',
                        adjudication='unresolved; both readings defensible; frozen labels unchanged',
                        explanation=reason,evidence=ev[(a['cp'],r)]['evidence'],
                        original_raw_file=f'docs/research/rule-learning-20261028/grade/run-D/seg-1/labels.json',
                        original_json_pointer=f'/{a["cp"]-8}/labels/{r}/{field}',
                        published_json_pointer='/'+identity['run'].replace('~','~0').replace('/','~1')+f'/checkpoints/{a["cp"]}/{field}/{r}'))
    summaries[name]=dict(checkpoints=25,rule_slots=175,field_comparisons=525,
        differing_rule_slots=len(slots),matching_rule_slots=175-len(slots),
        field_differences={k:counts[k] for k in ('belief','notebook','source')},
        category_counts={'clear_error':0,'ambiguity':len(slots),'rubric_issue':0})

value={'correct':1.0,'partial':0.5,'wrong':0.0,'absent':0.0}
def score(row,field):return round(100*sum(value[x[field]] for x in row['labels'].values())/7,1)
curve=[]
for a,b,c,m in zip(ind,raw,pub['checkpoints'],meta['checkpoints']):
    assert score(b,'belief')==c['score'] and score(b,'notebook')==c['notebook_score']
    curve.append(dict(cp=a['cp'],actions=m['actions'],minutes=m['minutes'],
        independent_combined=score(a,'belief'),raw_combined=score(b,'belief'),published_combined=c['score'],
        independent_notebook=score(a,'notebook'),raw_notebook=score(b,'notebook'),published_notebook=c['notebook_score']))
with (OUT/'curve-comparison.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(curve[0]));w.writeheader();w.writerows(curve)

result=dict(run='run-D',identity=identity,comparison_started_after_freeze=True,
    freeze_sha256=freeze['sha256']['independent-labels.json'],compared_at_utc=datetime.now(timezone.utc).isoformat(),
    inputs_sha256=inputs,summaries=summaries,disagreements=diffs,
    unique_disagreement_slots=2,unresolved_disagreement_slots=2,unreviewed_slots=0,unassigned_labels=0,
    original_and_published_equal=True,published_run_specific_corrections=0,
    final_score=dict(independent=curve[-1]['independent_combined'],original=curve[-1]['raw_combined'],published=curve[-1]['published_combined']),
    counts={name:{field:dict(Counter(x[field] for row in data for x in row['labels'].values())) for field in ('belief','notebook','source')}
            for name,data in [('independent',ind),('original_raw',raw),('published_corrected',published)]},
    scope_note='curves-combined.json is the published combined/corrected series. curves.json is the older notebook-only series and is not counted as the corrected comparator.',
    shared_rubric_limitations=[
      {'rules':['K2'],'issue':'Compound rule includes orange crates never described in this run; walls-only knowledge stays partial. Not a label disagreement.'},
      {'rules':['K7'],'issue':'All-red-rings-caged agrees with observed equal ring/target counts but is incomplete versus all targets covered by either crate kind. Not a label disagreement.'}])
(OUT/'comparison.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

report='''# Independent full-run audit: run-D

Completed all 25 checkpoints (cp000-cp024), all notebook versions and all thinking, in sequence: **175/175 rule slots**. No unreviewed or unassigned entries. No gameplay, subagents, model CLIs, installations, or changes to original experiment/grading files.

Independent labels were frozen before reading original grades, identity, handoffs, or curves. SHA-256: `FREEZE_HASH`. The manifest also freezes evidence, reading coverage, source verification, rules, handoff, and pre-comparison ambiguity notes. The progress log preserves checkpoint saves and pre-freeze refinements.

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
'''.replace('FREEZE_HASH',freeze['sha256']['independent-labels.json'])
(OUT/'report.md').write_text(report,encoding='utf-8')
with (OUT/'independent-progress.md').open('a',encoding='utf-8') as f:
    f.write('\nComparison complete: run-D raw seg0/1/2 and published corrected series all covered. Two unique ambiguous K4 disagreements (cp011,012); zero notebook/source differences. No established clear original grading errors. Frozen artifacts unchanged.\n')
for name,digest in freeze['sha256'].items():assert sha(OUT/name)==digest
for name,digest in inputs.items():assert sha(ROOT/name)==digest
print(json.dumps({'status':'PASS','summaries':summaries,'unique_disagreement_slots':2,'final_score':result['final_score']},indent=2))
