import json,pathlib,hashlib,collections,runpy,sys,io,contextlib
from unittest.mock import patch
root=pathlib.Path.cwd();p=root/'docs/research/rule-learning-audit-20261104/by-run/run-B'
def read(x):return json.loads(x.read_text(encoding='utf-8-sig'))
a=read(p/'independent-labels.json');old=read(p/'prior-000-024.json');inv={x['cp']:x for x in read(root/'docs/research/rule-learning-audit-20261104/inventory.json') if x['run']=='run-B'}
issues=[];quotes=[];hashes=[]
assert a[:25]==old,'Prior labels changed'
assert [x['cp'] for x in a]==list(range(29))
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
for cp in range(29):
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
with patch('builtins.open',audit_open),patch('glob.glob',return_value=[f'cp-{i:03d}.md' for i in range(29)]),patch('os.path.exists',return_value=False),patch.object(sys,'argv',[str(checker),'independent-audit']),contextlib.redirect_stdout(out):
 runpy.run_path(str(checker),run_name='__main__')
checker_result=out.getvalue().strip();assert checker_result=='ok: 29 checkpoints x 7 rules',checker_result

assert not issues,issues
result=dict(status='PASS',checkpoints=29,slots=203,prior175_preserved=a[:25]==old,quote_matches=quotes,input_hashes=hashes,rubric_checker=checker_result,issues=issues)
(p/'validation-final.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('quote_matches','input_hashes')}))
