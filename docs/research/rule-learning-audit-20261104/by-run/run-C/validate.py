import json,hashlib,shutil,subprocess
from pathlib import Path
O=Path(__file__).resolve().parent; R=O.parents[4]
rows=json.loads((O/'independent-labels.json').read_text(encoding='utf-8'))
inv=[x for x in json.loads((R/'docs/research/rule-learning-audit-20261104/inventory.json').read_text()) if x['run']=='run-C']
errs=[]; nq=0
assert [r['cp'] for r in rows]==[r['cp'] for r in inv]==list(range(33))
for r,x in zip(rows,inv):
 assert set(r['labels'])==set(x['rules'])
 for k,v in r['labels'].items():
  for e in v['evidence']+v['notebook_evidence']:
   nq+=1;t=(R/e['path']).read_text(encoding='utf-8');lines=t.splitlines()
   if e['cp']>r['cp']:errs.append([r['cp'],k,'future evidence',e])
   if e['quote'] not in lines[e['line']-1]:errs.append([r['cp'],k,'line mismatch',e])
   marker=t[:t.index('## Thinking written')].count('\n')+1
   if (e['channel']=='thinking') != (e['line']>marker):errs.append([r['cp'],k,'channel mismatch',e])
  if v['note']:
   q=v['note'][3:]
   if len(q.split())>20:errs.append([r['cp'],k,'note too long',len(q.split())])
   if not any(e['quote']==q for e in v['evidence']):errs.append([r['cp'],k,'note quote mismatch',q])
  if v['belief']!='absent' and not v['evidence']:errs.append([r['cp'],k,'missing evidence'])
  if v['notebook']!='absent' and not v['notebook_evidence']:errs.append([r['cp'],k,'missing notebook evidence'])
fixture=O/'validation-input';fixture.mkdir(exist_ok=True)
for x in inv: shutil.copyfile(R/x['path'],fixture/Path(x['path']).name)
shutil.copyfile(R/'docs/research/rule-learning-20261028/grade/run-C/seg-0/rules.json',fixture/'rules.json')
shutil.copyfile(O/'labels.json',fixture/'labels.json')
proc=subprocess.run([str(R/'.venv/Scripts/python.exe'),str(R/'docs/research/rule-learning-20261028/grade/check.py'),str(fixture)],capture_output=True,text=True)
result=dict(checkpoints=len(rows),rules=8,slots=264,unreviewed=0,quote_occurrences_validated=nq,errors=errs,official_checker_output=proc.stdout.strip(),official_checker_returncode=proc.returncode)
(O/'validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(result,indent=2,ensure_ascii=True))
