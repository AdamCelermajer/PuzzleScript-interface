import json,pathlib,copy
root=pathlib.Path.cwd(); b=root/'docs/research/rule-learning-audit-20261104/by-run/run-B'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
inv={x['cp']:x for x in read(root/'docs/research/rule-learning-audit-20261104/inventory.json') if x['run']=='run-B'}
def save(cp,changes,notebook_cp):
 a=read(b/'independent-labels.json'); assert a[-1]['cp']==cp-1
 labels=copy.deepcopy(a[-1]['labels'])
 for r,v in labels.items(): v['notebook_cp']=notebook_cp
 for r,v in changes.items():
  labels[r].update(v)
  if 'note' in v:
   e=labels[r]; ec=e['evidence_cp']; s=(root/inv[ec]['path']).read_text(encoding='utf-8'); q=e['note'][3:]; assert q in s and len(q.split())<=20
   e['evidence_path']=inv[ec]['path']; e['evidence_line']=s[:s.index(q)].count('\n')+1
 a.append(dict(cp=cp,labels=labels)); (b/'independent-labels.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 p=read(b/'progress.json'); p.update(graded_slots=len(a)*7,completed=list(range(cp+1)),unreviewed_slots=(29-len(a))*7,next=cp+1); (b/'progress.json').write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8'); print('Saved',cp)
save(15,{
 'I4':dict(note='T: box is blocked by (5,4) box',evidence_cp=15,explanation='Still predicts adjacent movable crates cannot push together (line 704).'),
 'I5':dict(note='T: Also... the creature passed through vertically in blue (c4)',evidence_cp=15,explanation='L5 blue blocking learned, but explicit L4 blue vertical-passage belief persists; partial, not universal blocking.'),
 'I6':dict(note='T: gold door = horizontal passage open (at least in the direction of exit)!',evidence_cp=15,explanation='Reinterprets L4 gold exit correctly; broader gold entry remains probably/conditional and blue vertical-passage exception persists. Partial retained.')
},13)
