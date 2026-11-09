import json,pathlib,copy
O=pathlib.Path(__file__).parent
old=json.loads((O/'before-60-independent-labels.json').read_text(encoding='utf-8'))
new=json.loads((O/'independent-labels.json').read_text(encoding='utf-8'))
for cp in range(60,65):
 row=new[cp]; row['labels']=copy.deepcopy(old[-1]['labels'])
 for v in row['labels'].values(): v.pop('note',None)
 if cp>=63:
  p=O.parents[4]/'docs/research/rule-learning-20261028/grade/run-E/seg-6/cp-063.md'; t=p.read_text(encoding='utf-8'); q='Given that in the actual game, blocked pushes were box-forward walls'
  row['labels']['M6']['evidence']=dict(cp=63,path=str(p.relative_to(O.parents[4])).replace('\\','/'),line=t[:t.index(q)].count('\n')+1,quote=q,kind='T')
 old.append(row)
(O/'independent-labels.json').write_text(json.dumps(old,indent=2),encoding='utf-8')
