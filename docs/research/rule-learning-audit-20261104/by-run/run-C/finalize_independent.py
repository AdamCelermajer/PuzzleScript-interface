import json,hashlib,re
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
rows=json.loads((OUT/'independent-labels.json').read_text(encoding='utf-8'))
inv=[x for x in json.loads((ROOT/'docs/research/rule-learning-audit-20261104/inventory.json').read_text()) if x['run']=='run-C']
texts=[(ROOT/x['path']).read_text(encoding='utf-8') for x in inv]
def ev(cp,q,ch):
 t=texts[cp]; assert q in t,(cp,q)
 return dict(cp=cp,path=inv[cp]['path'],line=t[:t.index(q)].count('\n')+1,quote=q,channel=ch)
extras={
 'M1':[ev(0,'ACTION1 = up.','thinking'),ev(0,'ACTION3 = left.','thinking'),ev(0,'ACTION2 = down','thinking'),ev(0,'ACTION7 on the checkerboard = launch player left','thinking')],
 'M2':[ev(0,'To push the box, I need to be on the opposite side.','thinking')],
 'M3':[ev(0,'If I push left, the box goes off-grid. So I can\'t push it left.','thinking'),ev(0,"push O up into B's cell? No, B is there.",'thinking')],
 'M6':[ev(2,"if the player's destination is blocked, the push is invalid.",'thinking'),ev(2,'Player (1,3)'+chr(0x2192)+'(1,2) [both black, OK].','thinking')],
 'M7':[ev(2,"I'll assume the box can cross (it must, for solvability).",'thinking')],
 'M8':[ev(2,'When the box was pushed onto the goal, level cleared.','thinking')]
}
notebook=None; nbcp=None
for row in rows:
 cp=row['cp'];t=texts[cp]
 nb=t.split('## Notebook',1)[1].split('## Thinking written',1)[0]
 if 'NEW VERSION' in nb: notebook=nb;nbcp=cp
 elif '(unchanged since' not in nb:
  if '(no notebook written yet)' not in nb.lower(): print('CHECK INITIAL NOTEBOOK',cp,repr(nb[:120]))
 for k,v in row['labels'].items():
  if k=='M5' and 6<=cp<=13: v['notebook']='correct';v['source']='both'
  if k=='M6' and cp==6: v['notebook']='absent';v['source']='thinking';v['note']=''
  if k=='M4' and cp==10: v['source']='notebook'
  for e in extras.get(k,[]):
   if e['cp']<=cp and e not in v['evidence']:v['evidence'].append(e)
  if k=='M6': v['evidence']=[e for e in v['evidence'] if not(e['cp']==6 and e['channel']=='notebook')]
  if v['belief']=='absent':v['note']=''
  # Every positive notebook grade receives a current notebook citation; unchanged notebooks resolve to their supplied version.
  v['notebook_evidence']=[]
  if v['notebook']!='absent':
   candidates={
    'M1':['ACTION1=UP'], 'M2':['Pushing: walk into box','Push: walk into box'],
    'M3':['Pushing: walk into box','Push: walk into box'],
    'M4':['Player cannot cross specific','Player CANNOT directly cross','So region rule must be wrong/limited.','individual HIDDEN WALLS','L1 observed blocks:','BOUNDARY RULE (observed L1)'],
    'M5':['Door (4,0) connects','Door (checkerboard','Door/checkerboard','checkerboard door cell (freely passable all directions).'],
    'M6':['Walking and PUSHING both blocked','keep PUSHER on same-color floors','pusher stays on same-color floors','Push box (4,2)up from (5,2)','Up-push at col2 blocked','crossing blocked','ROUTE A in progress:','T106: push box','push box (3,3)L'],
    'M7':['Boxes cross white/black boundary freely','Box CAN cross black/white color boundary','Box can cross black/white boundary freely','L2 plan assumes YES','CONFIRMED YES (L2: box'],
    'M8':['Push box(es)','Sokoban: push','Win: box lands','box on goal => instant next level']
   }[k]
   found=None
   for s in candidates:
    if s in notebook:
     rest=notebook[notebook.index(s):].split('\n')[0]
     found=' '.join(rest.split()[:20]);break
   assert found,(cp,k)
   v['notebook_evidence']=[ev(nbcp,found,'notebook')]
  v['decision_basis']={
   'M1':'Four directions known; no adopted no-action rule. ACTION7 special-tile interpretation persists. Partial credit; action versus undo naming is a rubric ambiguity.',
   'M2':'One-cell walk-into-crate push known/adopted. No explicit no-pull belief identified; strict compound-rule partial credit. Push-only deadlock reasoning is a plausible implicit alternative.',
   'M3':'Crate collision and off-grid refusal adopted in cp000 reasoning; generic rule persists despite initial blue-object misidentification. Notebook free-destination clause earns partial without explicit grid bound.',
   'M4':'Two-way colour boundary initially adopted. Mere doubt at cp006 does not erase it; explicit rejection/limitation at cp010 changes combined grade to partial. Later per-edge walls are correct effects with wrong scope.',
   'M5':'Checkerboard door is grey by verified source. Its two-way connection between white and black earns correct even with different vocabulary; passing doubts do not replace it.',
   'M6':'No adopted floor-specific push belief before cp002. Then same-colour cases and cross-colour refusals known, but grey-black push incompatibility never learned. Walking legality as sufficient for pushing is incomplete.',
   'M7':'Before cp002 alternatives are experiments. At cp002 explicit solvability working assumption allows crate boundary crossing, confirmed cp003; unrestricted destination interpretation maintained. cp031 temporary contradiction corrected within window.',
   'M8':'Before cp002 possible goal hypotheses are experiments, not adopted. cp002 identifies Sokoban boxes-to-blue-goals and next-level transition. Plural goal statement treated as essential completion condition; no competing one-of-many condition adopted.'
  }[k]
(OUT/'independent-labels.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
(OUT/'labels.json').write_text(json.dumps([dict(cp=r['cp'],labels={k:{f:v[f] for f in ['belief','source','notebook','note']} for k,v in r['labels'].items()}) for r in rows],indent=2,ensure_ascii=False),encoding='utf-8')
manifest=[dict(x,sha256=hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest(),lines=len(texts[i].splitlines()),characters=len(texts[i]),full_read=True) for i,x in enumerate(inv)]
(OUT/'reading-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(OUT/'pre-freeze-review.json').write_text(json.dumps({'prior_original_labels_read':False,'changes':[{'cp':list(range(6,14)),'rule':'M5','field':'notebook','from':'partial','to':'correct','reason':'Explicit two-way white/door/black connectivity is the essential rule.'},{'cp':[6],'rule':'M6','field':'notebook','from':'partial','to':'absent','reason':'Strict-rule push analysis is conditional, not adopted in this notebook.'},{'cp':[10],'rule':'M4','field':'source','from':'both','to':'notebook','reason':'New notebook rejects the global rule; earlier thinking had retained it.'}],'interpretation_questions':['M1 action button versus ACTION7 undo vocabulary','M2 whether push-only deadlock reasoning suffices for no-pull clause','M8 plural boxes-to-goals versus explicit universal quantifier']},indent=2),encoding='utf-8')
print('Prepared',len(rows),'checkpoints')





