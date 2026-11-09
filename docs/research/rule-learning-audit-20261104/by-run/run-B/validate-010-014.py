import json,pathlib,hashlib,collections,runpy,sys,io,contextlib
from unittest.mock import patch
root=pathlib.Path.cwd();p=root/'docs/research/rule-learning-audit-20261104/by-run/run-B'
def read(x):return json.loads(x.read_text(encoding='utf-8-sig'))
a=read(p/'independent-labels.json');old=read(p/'prior-000-009.json');inv={x['cp']:x for x in read(root/'docs/research/rule-learning-audit-20261104/inventory.json') if x['run']=='run-B'}
issues=[];quotes=[];hashes=[]
assert a[:10]==old,'Prior labels changed'
assert [x['cp'] for x in a]==list(range(15))
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
   if e['cp']>=10 and v.get('evidence_line')!=line:issues.append(f"Location {e['cp']} {r}: stored {v.get('evidence_line')} actual {line}")
   quotes.append(dict(cp=e['cp'],rule=r,evidence_cp=v['evidence_cp'],path=src,line=line,quote=q,exact_match=pos>=0))
for cp in range(15):
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
with patch('builtins.open',audit_open),patch('glob.glob',return_value=[f'cp-{i:03d}.md' for i in range(15)]),patch('os.path.exists',return_value=False),patch.object(sys,'argv',[str(checker),'independent-audit']),contextlib.redirect_stdout(out):
 runpy.run_path(str(checker),run_name='__main__')
checker_result=out.getvalue().strip();assert checker_result=='ok: 15 checkpoints x 7 rules',checker_result
result=dict(status='INCOMPLETE',bounded_batch_status='PASS' if not issues else 'FAIL',bounded_batch=[10,14],expected_checkpoints=29,reviewed_checkpoints=15,reviewed_slots=105,unreviewed_checkpoints=list(range(15,29)),unreviewed_slots=98,label_counts=dict(collections.Counter(v['belief'] for e in a for v in e['labels'].values())),issues=issues,quote_matches=quotes,input_hashes=hashes,requested_coverage=list(range(10,15)),requested_judgments=35,next_checkpoint=15,frozen=False,comparison_performed=False,prior_labels_preserved=a[:10]==old,prior_validation='validation-through-009.json',rubric_checker=checker_result,rubric_checker_adapter='Virtual labels/rules/checkpoint filenames; start.json existence forced false, no original labels or start opened.',full_reads={10:[1,509],11:[1,906],12:[1,207],13:[1,177],14:[1,731]})
(p/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:result[k] for k in ['bounded_batch_status','reviewed_slots','requested_judgments','prior_labels_preserved','rubric_checker','issues']}))
