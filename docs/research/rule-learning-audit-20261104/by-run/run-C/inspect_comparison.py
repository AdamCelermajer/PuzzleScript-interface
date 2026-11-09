import json
from pathlib import Path
R=Path.cwd();O=R/'docs/research/rule-learning-audit-20261104/by-run/run-C'
a=json.loads((O/'labels.json').read_text());b=[]
for p in sorted((R/'docs/research/rule-learning-20261028/grade/run-C').glob('seg-*/labels.json')):b+=json.loads(p.read_text(encoding='utf-8'))
for x,y in zip(a,b):
 d={k:{f:[y['labels'][k].get(f),v[f]] for f in ['belief','notebook','source'] if y['labels'][k].get(f)!=v[f]} for k,v in x['labels'].items()}
 print(x['cp'],{k:v for k,v in d.items() if v})
for name in ['curves.json','curves-combined.json']:
 d=json.loads((R/'docs/research/rule-learning-20261028'/name).read_text(encoding='utf-8'))
 print(name,type(d).__name__,list(d)[:15] if isinstance(d,dict) else len(d))
 if isinstance(d,dict):
  for k,v in d.items():print('KEY',k,type(v).__name__,str(v)[:700])
 else: print(str(d[0])[:2000])
