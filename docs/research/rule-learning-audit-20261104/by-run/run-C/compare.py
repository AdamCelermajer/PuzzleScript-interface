import json,hashlib,csv,collections,datetime
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[4];D=R/'docs/research/rule-learning-20261028'
frozen=json.loads((O/'freeze.json').read_text())
for n,h in frozen['files'].items():assert hashlib.sha256((O/n).read_bytes()).hexdigest()==h,n
ind=json.loads((O/'independent-labels.json').read_text(encoding='utf-8'));raw=[];inputs={}
for p in sorted((D/'grade/run-C').glob('seg-*/labels.json')):
 raw+=json.loads(p.read_text(encoding='utf-8'));inputs[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
p=D/'curves-combined.json';inputs[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
curve=[(k,v) for k,v in json.loads(p.read_text(encoding='utf-8')).items() if v['blind_id']=='C'];assert len(curve)==1
key,curve=curve[0];pub=curve['checkpoints'];assert [r['cp'] for r in ind]==[r['cp'] for r in raw]==[r['cp'] for r in pub]

def classification(cp,k,field):
 if k=='M2':return 'rubric_issue','The no-pull clause is not explicit. Independent grading requires it; original grading credits Sokoban/push wording as sufficient. Implicit push-only deadlock reasoning makes this a rubric threshold, not a clear original error.'
 if k=='M3' and cp<2:return 'ambiguity','Off-grid refusal and box-on-box refusal are explicit, but the putative blue box is actually a goal. Independent grading credits the generic collision belief; original partial may penalize object misidentification.'
 if k=='M3':return 'rubric_issue','Notebook says destination free, without explicit off-grid refusal. Whether free includes an existing in-bounds cell is an implicit-content threshold; source difference follows that label choice.'
 if k=='M7':return 'ambiguity','Notebook places the crossing question under Uncertain but explicitly says L2 plan assumes YES and uses it. Independent grading treats the adopted plan as a belief; original notebook partial is stricter.'
 if k=='M6':return 'clear_error','Original correct credits only white/black cases. The rule also requires grey-black push refusal, which is never distinguished from legal walking. Same-colour pusher reasoning is substantial but incomplete. Source differences follow the combined grade.'
 if k=='M4' and cp==10:return 'clear_error','This checkpoint has no new thinking. Its NEW notebook explicitly rejects/limits the prior global rule; the new partial belief is supported by notebook, not by carried correct thinking.'
 if k=='M4' and cp in [7,8,9]:return 'ambiguity','Current notebook retains a doubtful/conditional global rule while confirming individual blocked edges. Independent notebook grade is partial; original may infer renewed universal adoption from the ACTION7 conclusion. Combined belief agrees by persistence.'
 if k=='M4' and cp in [26,27]:return 'ambiguity','A local L4 assume-all-boundaries working assumption coexists with the explicit not-a-universal-rule clause and an open goal-edge probe. Scope and precedence within this notebook are ambiguous.'
 if k=='M4' and cp>=28:return 'clear_error','The rewritten notebook states specific per-level walls and only guaranteed door passage; all L4 boundaries are under unconfirmed hypotheses. Original notebook correct overstates scope. At cp028-030 combined correct also conflicts with the new notebook; cp031-032 combined partial agrees but source differs.'
 raise AssertionError((cp,k,field))

diffs=[];rawpub=[];scores=[];val={'correct':1,'partial':.5,'wrong':0,'absent':0}
for a,b,c in zip(ind,raw,pub):
 cp=a['cp']; assert set(a['labels'])==set(b['labels'])==set(c['belief'])
 for k,v in a['labels'].items():
  for field in ['belief','notebook','source']:
   if b['labels'][k][field]!=c[field][k]:rawpub.append(dict(cp=cp,rule=k,field=field,raw=b['labels'][k][field],published=c[field][k]))
   for target,old in [('raw',b['labels'][k][field]),('published',c[field][k])]:
    if v[field]!=old:
     cat,why=classification(cp,k,field)
     diffs.append(dict(target=target,cp=cp,rule=k,field=field,original=old,independent=v[field],classification=cat,explanation=why,original_note=b['labels'][k].get('note',''),checkpoint_path=next(x['path'] for x in json.loads((O/'reading-manifest.json').read_text()) if x['cp']==cp),evidence=v['evidence'],notebook_evidence=v['notebook_evidence']))
 score=lambda field:100*sum(val[v[field]] for v in a['labels'].values())/8
 scores.append(dict(cp=cp,actions=c['actions'],published_belief=c['score'],independent_belief=score('belief'),published_notebook=c['notebook_score'],independent_notebook=score('notebook'),published_belief_unrounded=100*sum(val[x] for x in c['belief'].values())/8))
 assert abs(c['score']-scores[-1]['published_belief_unrounded'])<=.051
assert not rawpub
rd=[d for d in diffs if d['target']=='raw']
counts=lambda field:dict(collections.Counter(d[field] for d in rd))
slotcats={cat:len({(d['cp'],d['rule']) for d in rd if d['classification']==cat}) for cat in ['clear_error','ambiguity','rubric_issue']}
summary=dict(run='run-C',checkpoints=33,rules=8,slots=264,compared_fields=792,unreviewed=0,unresolved_validation_entries=0,raw_published_differences=0,different_slots=len({(d['cp'],d['rule']) for d in rd}),field_disagreements=len(rd),by_field=counts('field'),by_rule=counts('rule'),by_classification_fields=counts('classification'),by_classification_slots=slotcats,unresolved_interpretive_slots=slotcats['ambiguity']+slotcats['rubric_issue'],independent_belief_counts=dict(collections.Counter(v['belief'] for r in ind for v in r['labels'].values())),independent_notebook_counts=dict(collections.Counter(v['notebook'] for r in ind for v in r['labels'].values())),raw_belief_counts=dict(collections.Counter(v['belief'] for r in raw for v in r['labels'].values())),published_curve_key=key,inputs_sha256=inputs,freeze_hashes_verified=True,scoring='correct=1, partial=0.5, wrong/absent=0; divide by 8. Original published scores rounded to 1 decimal; independent values exact.')
for name,obj in [('disagreements.json',diffs),('comparison-summary.json',summary),('curve-comparison.json',scores)]: (O/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
with (O/'disagreements.csv').open('w',newline='',encoding='utf-8-sig') as f:
 fields=['target','cp','rule','field','original','independent','classification','explanation','checkpoint_path'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(diffs)
with (O/'curve-comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(scores[0]));w.writeheader();w.writerows(scores)
print(json.dumps(summary,indent=2));print('FINAL SCORE',scores[-1])
