import json,pathlib,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[5]
OUT=pathlib.Path(__file__).resolve().parent
INV=[x for x in json.loads((ROOT/'docs/research/rule-learning-audit-20261104/inventory.json').read_text()) if x['run']=='run-C']
def save(cp, specs, rationale):
 p=OUT/'independent-labels.json'
 rows=json.loads(p.read_text()) if p.exists() else []
 assert cp==len(rows)
 labels={}
 for i,(belief,quote) in enumerate(specs,1):
  rule='M'+str(i)
  prev=rows[-1]['labels'][rule] if rows else None
  if quote=='persist':
   labels[rule]=dict(prev); labels[rule]['note']=''; continue
  ev=[]
  if quote:
   text=(ROOT/INV[cp]['path']).read_text(encoding='utf-8')
   assert quote in text,(cp,rule,quote)
   ev=[{'cp':cp,'path':INV[cp]['path'],'line':text[:text.index(quote)].count('\n')+1,'quote':quote,'channel':'thinking'}]
  labels[rule]={'belief':belief,'source':'none' if belief=='absent' else 'thinking','notebook':'absent','note':'T: '+quote if quote else 'No adopted belief after full reading.','evidence':ev}
 rows.append({'cp':cp,'labels':labels,'rationale':rationale})
 p.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
 (OUT/'progress.json').write_text(json.dumps({'completed':len(rows),'total':len(INV),'last_cp':cp,'frozen':False},indent=2))
 (OUT/'current-belief-handoff.md').write_text(f'Independent audit through cp-{cp:03d}; {len(rows)}/{len(INV)} complete.\n'+rationale+'\n'+ '\n'.join(f'{k}: {v["belief"]}; evidence {v["evidence"]}' for k,v in labels.items()),encoding='utf-8')

