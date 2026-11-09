"""Compare frozen run-F labels only. Does not change original or frozen labels."""
from pathlib import Path
import json,hashlib,csv,collections,datetime
ROOT=Path(__file__).resolve().parents[5];OUT=Path(__file__).resolve().parent;BASE=ROOT/'docs/research/rule-learning-20261028'
load=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=load(OUT/'freeze.json');assert sha(OUT/'labels.json')==f['labels_sha256']
a=load(OUT/'labels.json');inv=load(OUT/'inventory.json');rawfiles=sorted((BASE/'grade/run-F').glob('seg-*/labels.json'))
inputs=rawfiles+[BASE/'curves-combined.json',BASE/'grade/key.json',BASE/'combine.py']
before={str(p.relative_to(ROOT)):sha(p) for p in inputs}
raw={r['cp']:r['labels'] for p in rawfiles for r in load(p)}
key=load(BASE/'grade/key.json')['F'];published=load(BASE/'curves-combined.json')[key['run']];assert published['blind_id']=='F'
pc={r['cp']:r for r in published['checkpoints']};pub={cp:{rid:{fld:r[fld][rid] for fld in ['belief','notebook','source']} for rid in r['belief']} for cp,r in pc.items()}
assert set(raw)==set(pub)==set(range(32))
texts={x['cp']:(ROOT/x['path']).read_text(encoding='utf-8') for x in inv}
def ev(cp,q):
 s=texts[cp];at=s.index(q);return {'cp':cp,'path':inv[cp]['path'],'section':'notebook' if at<s.index('## Thinking') else 'thinking','quote':q,'line':s[:at].count('\n')+1}
extra=ev(7,'Most likely: a timing gate (a door that opens/cycles on a period-3 timer)')
def classify(target,cp,rid,field):
 if rid=='I2':return 'rubric_issue','Composite-rule granularity: frozen grade requires wall/water/immovable-crate applicability; original credits generic sliding-to-blocker knowledge. State the policy before adjudicating.'
 if rid=='I3':return 'ambiguity','cp5 adopts pushability as necessary, then entertains alternatives. Frozen grade treats adoption as persistent working belief; absent is plausible if interpreted as exploratory.'
 if rid=='I7':return 'ambiguity','Feeding becomes the selected/remaining L4 objective in thinking, but correct stop-on-plant evidence persists for earlier levels. Commitment versus continued exploration is interpretive.'
 if rid=='I5' and target=='raw' and cp==7 and field=='belief':return 'ambiguity','Blocking is directly recognized; later most-likely timing-gate model suggests passable phases. Correct versus partial depends on whether that account is adopted.'
 if rid=='I5':return 'clear_error',('Published correction deletes actual blue-water blocking belief at cp7; full trace states that the blue object stops the slide. Partial versus correct may be debated, absent is unsupported.' if target=='published' else 'Raw grade attributes fixed dark wall/pit geometry to water. Notebook through cp11 has no blue-water rule; cp7 water belief is thinking-only.')
 raise AssertionError((target,cp,rid,field))
all_diffs={};summary={}
for name,target in [('raw',raw),('published',pub)]:
 diffs=[]
 for row in a:
  cp=row['cp']
  for rid,v in row['labels'].items():
   for fld in ['belief','notebook','source']:
    if v[fld]==target[cp][rid][fld]:continue
    category,reason=classify(name,cp,rid,fld)
    evidence=list(v['evidence'])
    if rid=='I5' and cp==7:evidence.append(extra)
    diffs.append({'cp':cp,'rule':rid,'field':fld,'original':target[cp][rid][fld],'independent':v[fld],'category':category,'reason':reason,'evidence':evidence,'absence_rationale':v.get('absence_rationale'),'original_note':raw[cp][rid].get('note',''),'published_correction':pc[cp].get('corrected',{}).get(rid)})
 all_diffs[name]=diffs
 summary[name]={'field_disagreements':len(diffs),'rule_checkpoint_slots_with_disagreement':len({(x['cp'],x['rule']) for x in diffs}),'by_field':dict(collections.Counter(x['field'] for x in diffs)),'by_category_fields':dict(collections.Counter(x['category'] for x in diffs)),'by_category_slots':{cat:len({(x['cp'],x['rule']) for x in diffs if x['category']==cat}) for cat in ['clear_error','ambiguity','rubric_issue']},'original_belief_counts':dict(collections.Counter(v['belief'] for r in target.values() for v in r.values()))}
VAL={'correct':1,'partial':.5,'wrong':0,'absent':0}
def score(vals):return round(100*sum(VAL[x] for x in vals)/7,1)
curves=[]
for row in a:
 cp=row['cp'];c=pc[cp];ours=score(v['belief'] for v in row['labels'].values());oursn=score(v['notebook'] for v in row['labels'].values())
 curves.append({'cp':cp,'actions':c['actions'],'minutes':c['minutes'],'raw_score':score(v['belief'] for v in raw[cp].values()),'published_score':c['score'],'independent_score':ours,'published_notebook_score':c['notebook_score'],'independent_notebook_score':oursn,'score_delta':round(ours-c['score'],1),'notebook_score_delta':round(oursn-c['notebook_score'],1)})
assert all(score(v['belief'] for v in pub[cp].values())==pc[cp]['score'] for cp in pc)
assert all(score(v['notebook'] for v in pub[cp].values())==pc[cp]['notebook_score'] for cp in pc)
report={'run':'run-F','identity':key,'labels_sha256':f['labels_sha256'],'comparison_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'coverage':{'checkpoints':32,'rules':7,'slots':224,'unreviewed':0},'summary':summary,'published_score_points_different':sum(x['score_delta']!=0 for x in curves),'published_notebook_points_different':sum(x['notebook_score_delta']!=0 for x in curves),'disagreements':all_diffs,'curves':curves,'unresolved_adjudication':{'definition':'Assigned independent labels are final; these differences need human rubric/interpretation adjudication, not more unread slots. Fields can share one rule/checkpoint slot.','raw_field_entries':sum(x['category']!='clear_error' for x in all_diffs['raw']),'published_field_entries':sum(x['category']!='clear_error' for x in all_diffs['published']),'raw_unique_slots':len({(x['cp'],x['rule']) for x in all_diffs['raw'] if x['category']!='clear_error'}),'published_unique_slots':len({(x['cp'],x['rule']) for x in all_diffs['published'] if x['category']!='clear_error'})},'read_only_inputs_sha256':before}
assert before=={str(p.relative_to(ROOT)):sha(p) for p in inputs};assert sha(OUT/'labels.json')==f['labels_sha256']
report['original_inputs_unchanged']=True
(OUT/'comparison.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
with (OUT/'disagreements.csv').open('w',newline='',encoding='utf-8') as fh:
 fields=['target','cp','rule','field','original','independent','category','reason'];w=csv.DictWriter(fh,fieldnames=fields);w.writeheader()
 for target,rows in all_diffs.items():
  for r in rows:w.writerow({'target':target,**{k:r[k] for k in fields if k!='target'}})
with (OUT/'curve-comparison.csv').open('w',newline='',encoding='utf-8') as fh:
 w=csv.DictWriter(fh,fieldnames=list(curves[0]));w.writeheader();w.writerows(curves)
print(json.dumps({k:v for k,v in report.items() if k not in ['disagreements','curves','read_only_inputs_sha256']},indent=2))
