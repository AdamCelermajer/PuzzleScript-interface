import json,pathlib,collections
O=pathlib.Path(__file__).parent;R=O.parents[4];G=R/'docs/research/rule-learning-20261028'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
ind=read(O/'frozen-independent-labels.json');raw={x['cp']:x for p in (G/'grade/run-E').glob('seg-*/labels.json') for x in read(p)}; pub=next(v for v in read(G/'curves-combined.json').values() if v['blind_id']=='E')['checkpoints']
for name,rows in [('raw',raw),('published',{x['cp']:dict(labels={r:{f:x[f][r] for f in ['belief','source','notebook']} for r in x['belief']}) for x in pub})]:
 groups=collections.defaultdict(list)
 for x in ind:
  for r,v in x['labels'].items():
   for f in ['belief','notebook','source']:
    if v[f]!=rows[x['cp']]['labels'][r][f]:groups[(r,f,rows[x['cp']]['labels'][r][f],v[f])].append(x['cp'])
 print(name)
 for k,v in groups.items(): print(k,v)
print('published corrections',[(x['cp'],x['corrected']) for x in pub if x.get('corrected')])
print('independent rationales');
for x in ind[:40]:print(x['cp'],x['rationale'])
