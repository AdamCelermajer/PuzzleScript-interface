import json, pathlib, hashlib
ROOT=pathlib.Path(__file__).resolve().parents[5]
OUT=pathlib.Path(__file__).parent
INV=[x for x in json.loads((ROOT/'docs/research/rule-learning-audit-20261104/inventory.json').read_text()) if x['run']=='run-E']
def read(cp):
 p=ROOT/INV[cp]['path']; return p.read_text(encoding='utf-8')
def save(cp, grades, quotes=None, rationale=''):
 p=OUT/'independent-labels.json'
 rows=json.loads(p.read_text()) if p.exists() else []
 assert len(rows)==cp
 labels={}
 for i,(b,n,s) in enumerate(grades,1):
  r='M'+str(i); q=(quotes or {}).get(r)
  labels[r]=dict(belief=b,notebook=n,source=s)
  if q:
   origin,kind,quote=q; txt=read(origin); assert quote in txt, (r,quote)
   labels[r]['evidence']=dict(cp=origin,path=INV[origin]['path'],line=txt[:txt.index(quote)].count('\n')+1,quote=quote,kind=kind)
   labels[r]['note']=kind+': '+quote
  elif b!='absent':
   labels[r]['evidence']=rows[-1]['labels'][r]['evidence']
  elif cp==0: labels[r]['note']='No adopted belief after complete reading; notebook explicitly lists everything as uncertain.'
 rows.append(dict(cp=cp,labels=labels,rationale=rationale,full_read=True))
 p.write_text(json.dumps(rows,indent=2),encoding='utf-8')
 (OUT/'progress.json').write_text(json.dumps(dict(completed=cp+1,total=len(INV),next_cp=cp+1,comparison_opened=False),indent=2))
 (OUT/'current-belief-handoff.md').write_text(f'Last fully read and graded checkpoint: {cp}. Next: {cp+1}.\n'+rationale+'\n'+'\n'.join(f'{r}: {v}' for r,v in labels.items()),encoding='utf-8')
if __name__=='__main__':
 for cp in [0,1]: save(cp,[('absent','absent','none')]*8,rationale='No adopted game-mechanics belief. Controls/objective remain explicitly unknown; alternatives are exploratory hypotheses.')
