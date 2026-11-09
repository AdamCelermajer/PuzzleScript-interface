import json,hashlib,pathlib,datetime,shutil,subprocess,sys
O=pathlib.Path(__file__).parent; R=O.parents[4]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v): (O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
rows=json.loads((O/'independent-labels.json').read_text(encoding='utf-8')); inv=[x for x in json.loads((R/'docs/research/rule-learning-audit-20261104/inventory.json').read_text(encoding='utf-8')) if x['run']=='run-E']; errors=[]; checks=[]; citations=[]; notes=[]
assert [r['cp'] for r in rows]==list(range(65))
assert rows[:60]==json.loads((O/'before-60-independent-labels.json').read_text(encoding='utf-8'))
texts={x['cp']:(R/x['path']).read_text(encoding='utf-8') for x in inv}
for x in inv:
 p=R/x['path']; ok=sha(p)==x['sha256'] and p.stat().st_size==x['bytes']; checks.append(dict(cp=x['cp'],path=x['path'],sha256=sha(p),matches=ok)); assert ok
for row in rows:
 cp=row['cp']; assert list(row['labels'])==[f'M{i}' for i in range(1,9)] and row['full_read']
 for rule,v in row['labels'].items():
  assert v['belief'] in ['correct','partial','wrong','absent'] and v['notebook'] in ['correct','partial','wrong','absent']
  assert v['source'] in ['none','both','notebook','thinking']
  for ev in ([v['evidence']] if 'evidence' in v else [])+v.get('supporting_evidence',[]):
   t=texts[ev['cp']]; ls=t.splitlines(); ok=ev['quote'] in ls[ev['line']-1] and ev['cp']<=cp and ev['path']==inv[ev['cp']]['path']; assert ok,(cp,rule,ev)
   assert ev['kind']==('N' if ev['line']<next(i for i,l in enumerate(ls,1) if l.startswith('## Thinking written')) else 'T')
   citations.append(dict(cp=cp,rule=rule,**{'evidence':ev},exact=True))
  if v.get('note','').startswith(('N: ','T: ')):
   q=v['note'][3:]; ok=len(q.split())<=20 and any(q in texts[k] for k in range(cp+1)); notes.append(dict(cp=cp,rule=rule,valid=ok));
   if not ok: errors.append(f'note {cp} {rule}')
fixture=O/'full-check'; fixture.mkdir(exist_ok=True)
for x in inv: shutil.copyfile(R/x['path'],fixture/f"cp-{x['cp']:03d}.md")
shutil.copyfile(R/'docs/research/rule-learning-20261028/grade/run-E/seg-6/rules.json',fixture/'rules.json'); shutil.copyfile(O/'independent-labels.json',fixture/'labels.json')
c=subprocess.run([sys.executable,str(R/'docs/research/rule-learning-20261028/grade/check.py'),str(fixture)],capture_output=True,text=True)
assert c.stdout.strip()=='ok: 65 checkpoints x 8 rules',c.stdout
prior=json.loads((O/'final-prior-output-hashes.json').read_text(encoding='utf-8')); preserved={}
for n,h in prior.items():
 p=O/('before-60-'+n) if n in ['independent-labels.json','progress.json','current-belief-handoff.md','README.md','validation.json'] else O/n
 preserved[n]=sha(p)==h
assert all(preserved.values())
write('final-validation.json',dict(coverage=520,checkpoints=65,prior_480_unchanged=True,prior_outputs_preserved=preserved,input_checks=checks,citation_checks=citations,note_checks=notes,errors=errors,checker_stdout=c.stdout,checker_exit=c.returncode,limitations=['Prior cp0-59 full-reading attestations inherited; this continuation read cp60-64 in full.','cp61 was displayed after cp60 had been judged but its first save attempt failed (Python alias absent); cp60 was saved with existing virtualenv before cp61 was graded.']))
assert not errors,errors
shutil.copyfile(O/'independent-labels.json',O/'frozen-independent-labels.json')
write('freeze.json',dict(frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),checkpoints=65,slots=520,comparison_opened=False,files={n:sha(O/n) for n in ['frozen-independent-labels.json','independent-labels.json','final-validation.json']},input_hashes=checks))
print('FROZEN',sha(O/'frozen-independent-labels.json'))

