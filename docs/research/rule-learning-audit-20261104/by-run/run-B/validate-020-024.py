import json,pathlib,hashlib,collections,runpy,sys,io,contextlib
from unittest.mock import patch
root=pathlib.Path.cwd();p=root/'docs/research/rule-learning-audit-20261104/by-run/run-B'
def read(x):return json.loads(x.read_text(encoding='utf-8-sig'))
a=read(p/'independent-labels.json');old=read(p/'prior-000-019.json');inv={x['cp']:x for x in read(root/'docs/research/rule-learning-audit-20261104/inventory.json') if x['run']=='run-B'}
issues=[];quotes=[];hashes=[]
assert a[:20]==old,'Prior labels changed'
assert [x['cp'] for x in a]==list(range(25))
prev={}
for e in a:
 assert set(e['labels'])==set(inv[e['cp']]['rules'])
 for r,v in e['labels'].items():
  assert v['belief'] in ['absent','wrong','partial','correct'] and v['notebook'] in ['absent','wrong','partial','correct']
  assert v['source'] in ['none','notebook','thinking','both']
  assert (v['belief']=='absent')==(v['source']=='none')
  if v['belief']!=prev.get(r):assert v.get('note')
  prev[r]=v['belief']
  if v['note'].startswith(('N: ','T: ')):
   q=v['note'][3:];src=inv[v['evidence_cp']]['path'];s=(root/src).read_text(encoding='utf-8');pos=s.find(q);line=s[:pos].count('\n')+1
   if pos<0:issues.append(f"Quote mismatch {e['cp']} {r}: {q}")
   if len(q.split())>20:issues.append(f"Quote length {e['cp']} {r}")
   if e['cp']>=20 and v.get('evidence_line')!=line:issues.append(f"Location {e['cp']} {r}: stored {v.get('evidence_line')} actual {line}")
   quotes.append(dict(cp=e['cp'],rule=r,evidence_cp=v['evidence_cp'],path=src,line=line,quote=q,exact_match=pos>=0))
for cp in range(25):
 x=inv[cp];b=(root/x['path']).read_bytes();h=hashlib.sha256(b).hexdigest();ok=h==x['sha256'] and len(b)==x['bytes'];assert ok
 hashes.append(dict(cp=cp,path=x['path'],sha256=h,bytes=len(b),inventory_match=ok))
# Run the rubric checker against the independent audit using virtual filenames.
# No original start.json or original labels are opened.
checker=root/'docs/research/rule-learning-20261028/grade/check.py';rulepath=root/'docs/research/rule-learning-20261028/grade/run-B/seg-1/rules.json'
original_open=open
def audit_open(name,*args,**kwargs):
 if str(name).endswith('/rules.json'):return original_open(rulepath,*args,**kwargs)
 if str(name).endswith('/labels.json'):return original_open(p/'independent-labels.json',*args,**kwargs)
 raise AssertionError('Unexpected checker read: '+str(name))
out=io.StringIO()
with patch('builtins.open',audit_open),patch('glob.glob',return_value=[f'cp-{i:03d}.md' for i in range(25)]),patch('os.path.exists',return_value=False),patch.object(sys,'argv',[str(checker),'independent-audit']),contextlib.redirect_stdout(out):
 runpy.run_path(str(checker),run_name='__main__')
checker_result=out.getvalue().strip();assert checker_result=='ok: 25 checkpoints x 7 rules',checker_result
result=dict(status='INCOMPLETE',bounded_batch_status='PASS' if not issues else 'FAIL',bounded_batch=[20,24],expected_checkpoints=29,reviewed_checkpoints=25,reviewed_slots=175,unreviewed_checkpoints=list(range(25,29)),unreviewed_slots=28,label_counts=dict(collections.Counter(v['belief'] for e in a for v in e['labels'].values())),issues=issues,quote_matches=quotes,input_hashes=hashes,requested_coverage=list(range(20,25)),requested_judgments=35,next_checkpoint=25,frozen=False,comparison_performed=False,prior_labels_preserved=a[:20]==old,prior_validation='validation-015-019.json',rubric_checker=checker_result,rubric_checker_adapter='Virtual labels/rules/checkpoint filenames; start.json existence forced false, no original labels or start opened.',full_reads={20:[1,1102],21:[1,248],22:[1,782],23:[1,1141],24:[1,438]},resolved_notebook=dict(inherited_cp=13,inherited_lines=[1,173],new_cp=24,new_lines=[1,200]),new_judgments=35)
preserved=read(p/'preserved-020-024.json')
for name,h in preserved.items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==h, 'Preserved file changed: '+name
for e in a[20:]:
 for rule,v in e['labels'].items():
  assert v['evidence_path']==inv[v['evidence_cp']]['path']
  assert v['evidence_cp']<=e['cp']
  assert v['notebook_cp']==(24 if e['cp']==24 else 13)
result['preserved_file_hashes']=preserved
result['all_preserved_files_unchanged']=True
result['prior_judgments_preserved']=140
result['prior_snapshot_sha256']=hashlib.sha256((p/'prior-000-019.json').read_bytes()).hexdigest()
result['read_order_note']='Cp20 fully read and judged before cp21; initial cp20 save attempt failed on BOM before cp21 read, then cp20 saved followed by cp21. Cp22-24 each saved before next read.'
(p/'validation-020-024.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:result[k] for k in ['bounded_batch_status','reviewed_slots','requested_judgments','prior_labels_preserved','rubric_checker','issues']}))
