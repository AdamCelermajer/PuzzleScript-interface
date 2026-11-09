import json,hashlib,collections,datetime,csv
from pathlib import Path
root=Path.cwd();b=root/'docs/research/rule-learning-audit-20261104/by-run/run-B';g=root/'docs/research/rule-learning-20261028'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
freeze=read(b/'freeze.json')
for n,h in freeze['sha256'].items():assert hashfile(b/n)==h
A=read(b/'independent-labels.json');inv={x['cp']:x for x in read(root/'docs/research/rule-learning-audit-20261104/inventory.json') if x['run']=='run-B'}
files=sorted((g/'grade/run-B').glob('seg-*/labels.json'));O={};loc={}
for p in files:
 for i,e in enumerate(read(p)):
  assert e['cp'] not in O;O[e['cp']]=e['labels'];loc[e['cp']]={'path':p.relative_to(root).as_posix(),'json_pointer':f'/{i}/labels'}
key=read(g/'grade/key.json')['B'];pub=read(g/'curves-combined.json')[key['run']];P={e['cp']:{r:{f:e[f][r] for f in ('belief','notebook','source')} for r in e['belief']} for e in pub['checkpoints']}
assert set(O)==set(P)==set(range(29))
V=read(b/'validation-final.json');evidence={(e['cp'],e['rule']):e for e in V['quote_matches']}

def classify(cp,r,f):
 if r=='I2':
  return 'rubric_issue','I2 bundles sliding with all blocker types. Independent requires water/immovable-crate applicability; original credits the sliding core. False directional water or additional stopping conditions reduce completeness under the stricter reading.','Original correct is defensible if I2 measures only core sliding and leaves water to I5; source changes follow the chosen completeness threshold.'
 if r=='I1':
  return 'ambiguity','Cp0 calls four directions a hypothesis, leaves mapping UNKNOWN, and proposes probing. Independent excludes it as unconfirmed; rubric also accepts a single leading notebook hypothesis, making original correct defensible. Cp1 notebook unchanged, so notebook/source difference persists.','Accept the single leading hypothesis as belief (original correct); or require adoption beyond tentative probably/unconfirmed (independent absent). Do not call original clearly wrong.'
 if r=='I5' and cp in (5,6,7):
  return 'ambiguity','Cp5:319 concludes creature cannot pass in any state; independent treats it as a general adopted blocking belief. Original partial can read this as only tested leftward scope amid unresolved door theories.','Partial if direction-limited; correct if adopted general conclusion overrides speculative alternatives.'
 if r=='I5':
  return 'ambiguity','Cp20-22 general L5 blocking can supersede or coexist with older explicit L4 blue vertical passage. Cp28:10 explains gold conversion and :14 adopts opaque-blue working model, but still calls it conservative.','Original timing is defensible if new working models replace old exceptions earlier; cp28 partial is defensible if conservative implementation is not a revised belief.'
 if r=='I6':
  return 'ambiguity','Cp15:815 adopts horizontal gold exit, but :817 says probably both directions. Independent keeps partial through cp17; original accepts full floor-passability inference.','Correct if gold passability is sufficiently adopted; partial if unrestricted entry remains only tentative. Source difference follows grade.'
 if r in ('I3','I4'):
  return 'ambiguity','Cp20:1049-1051 and cp21:217,237-247 adopt incorrect approach/following positions despite substantial pushing knowledge. Independent reads these as partial beliefs; original may treat them as planning mistakes.','Correct if local coordinate/simulation slips do not revise mechanics; partial if executed/adopted predictions express current beliefs.'
 if r=='I7' and cp in (18,19) and f=='source':
  return 'clear_error','Independent source both conflicts with operational source definition: current notebook alone is correct, whereas newer thinking produces the partial combined grade. Original thinking is better supported.','Adjudicate source=thinking; retain frozen independent label unchanged. A broader contributory reading of both explains the mistake but differs from label-support convention.'
 return 'ambiguity','Cp11:687 and cp17:440 explicitly adopt non-plant objectives for the current level while retaining earlier plant wins. Independent reads an adopted exception; original may treat continued exploration as insufficient retraction.','Partial for adopted level exception; correct if these are exploratory alternatives rather than replacement beliefs.'

rows=[];slots=[];carry={}
for e in A:
 cp=e['cp']
 for r,v in e['labels'].items():
  if O[cp][r].get('note'):carry[r]={'cp':cp,'note':O[cp][r]['note']}
  slot={'cp':cp,'rule':r,'independent':v,'raw':O[cp][r],'published':P[cp][r],'raw_location':dict(loc[cp],json_pointer=loc[cp]['json_pointer']+'/'+r),'published_location':{'path':'docs/research/rule-learning-20261028/curves-combined.json','run_key':key['run'],'cp':cp,'rule':r},'independent_evidence':evidence.get((cp,r),{'path':inv[cp]['path'],'line':38 if cp==0 else None,'quote':'Hypothesis: 4 = 4 directions, 1 = other verb (interact/jump/toggle).','scope':'cp0 controls section and full checkpoint; no adopted belief under frozen interpretation'}),'original_carried_note':carry.get(r)}
  if cp==0:
   ev=slot['independent_evidence'];txt=(root/ev['path']).read_text(encoding='utf-8');ev['line']=txt[:txt.index(ev['quote'])].count('\n')+1
  slots.append(slot)
  for target,other in [('raw',O[cp][r]),('published',P[cp][r])]:
   for f in ('belief','notebook','source'):
    if v[f]==other[f]:continue
    cat,why,alt=classify(cp,r,f)
    rows.append(dict(target=target,cp=cp,rule=r,field=f,original=other[f],independent=v[f],classification=cat,rationale=why,reasonable_alternative=alt,evidence=slot['independent_evidence'],original_location=slot[target+'_location'] if target=='published' else slot['raw_location'],original_carried_note=slot['original_carried_note'],independent_explanation=v.get('explanation','')))
summary={}
for target in ('raw','published'):
 rs=[x for x in rows if x['target']==target];summary[target]={'compared_slots':203,'differing_slots':len({(x['cp'],x['rule']) for x in rs}),'fields':dict(collections.Counter(x['field'] for x in rs)),'total_field_differences':len(rs),'classification_fields':dict(collections.Counter(x['classification'] for x in rs))}
score=lambda labels,f:round(100*sum({'correct':1,'partial':.5,'absent':0,'wrong':0}[v[f]] for v in labels.values())/7,1)
curves=[]
for e in A:
 cp=e['cp'];pc=pub['checkpoints'][cp];d={'cp':cp,'actions':pc['actions']}
 for f in ('belief','notebook'):
  d['independent_'+f]=score(e['labels'],f);d['raw_'+f]=score(O[cp],f);d['published_'+f]=score(P[cp],f)
  assert d['published_'+f]==pc['score' if f=='belief' else 'notebook_score']
 curves.append(d)
inputs=files+[g/'curves-combined.json',g/'grade/key.json',g/'combine.py',g/'grade/INSTRUCTIONS.md',root/'puzzlescript_interface/games/ps_icecrates-v1/script.txt']
hashes={p.relative_to(root).as_posix():hashfile(p) for p in inputs}
result={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeze':freeze,'identity':key,'summary':summary,'raw_published_categorical_differences':sum(O[c][r][f]!=P[c][r][f] for c in O for r in O[c] for f in ('belief','notebook','source')),'slots':slots,'differences':rows,'curves':curves,'input_hashes':hashes,'limits':['Prior cp0-24 judgments inherited and preserved, not freshly regraded; prior full reads documented by earlier batch notes.','cp20 failed-save ordering caveat and cp10 recovery retained.','Categories are evidence-based audit assessments, not external adjudication.','No post-freeze independent edits.']}
(b/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,rs in [('disagreements.csv',rows),('curve-comparison.csv',curves)]:
 with (b/name).open('w',encoding='utf-8',newline='') as fp:
  writer=csv.DictWriter(fp,fieldnames=list(rs[0]));writer.writeheader();writer.writerows(rs)
# Separate source-field adjudication, including agreements that the two graders share.
adj=[]
for cp,r in [(17,'I7'),(18,'I7'),(19,'I7'),(20,'I3'),(21,'I3')]:
 adj.append({'cp':cp,'rule':r,'field':'source','frozen':A[cp]['labels'][r]['source'],'recommended':'thinking','classification':'source_attribution_correction','reason':'Current notebook alone earns correct; combined partial arises from newer thinking, so thinking supports the changed grade under operational label-support reading. Both is defensible only under a broader contribution interpretation.','evidence':evidence[(cp,r)]})
(b/'adjudication.json').write_text(json.dumps({'frozen_labels_edited':False,'source_corrections':adj,'interpretive_disagreements':'See comparison.json; no forced adjudication of ambiguity/rubric issues.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary));print('RAW-PUB',result['raw_published_categorical_differences']);print('FINAL',curves[-1]);print('COUNTS',collections.Counter(v['belief'] for e in A for v in e['labels'].values()))
