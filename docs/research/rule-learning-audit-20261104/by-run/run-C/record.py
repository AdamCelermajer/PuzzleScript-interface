import sys,json
sys.path.insert(0,'docs/research/rule-learning-audit-20261104/by-run/run-C')
from audit_helpers import *
def full(cp,bs,ns,quotes,reason):
 p=OUT/'independent-labels.json'; rows=json.loads(p.read_text()); assert len(rows)==cp
 t=(ROOT/INV[cp]['path']).read_text(encoding='utf-8'); labels={}
 for i,(b,n,q) in enumerate(zip(bs,ns,quotes),1):
  old=rows[-1]['labels']['M'+str(i)]; ev=list(old['evidence'])
  if q:
   ch,q=q.split(':',1); assert q in t,(cp,q)
   ev.append({'cp':cp,'path':INV[cp]['path'],'line':t[:t.index(q)].count('\n')+1,'quote':q,'channel':ch})
  labels['M'+str(i)]={'belief':b,'notebook':n,'source':'none' if b=='absent' else ('both' if b==n else 'thinking'),'note':(('N: ' if ch=='notebook' else 'T: ')+q) if q else '', 'evidence':ev}
 rows.append({'cp':cp,'labels':labels,'rationale':reason});p.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
 (OUT/'progress.json').write_text(json.dumps({'completed':len(rows),'total':33,'last_cp':cp,'frozen':False},indent=2))
 (OUT/'current-belief-handoff.md').write_text(f'Independent audit through cp-{cp:03d}. {len(rows)}/33 checkpoints. Not frozen.\n'+reason+'\n'+json.dumps(labels,ensure_ascii=False,indent=2),encoding='utf-8')