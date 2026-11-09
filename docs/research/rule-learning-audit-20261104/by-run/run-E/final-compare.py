import json,pathlib,hashlib,datetime,collections
O=pathlib.Path(__file__).parent;R=O.parents[4];G=R/'docs/research/rule-learning-20261028'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v):(O/n).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
f=read(O/'freeze.json'); assert all(sha(O/n)==h for n,h in f['files'].items())
inv=read(R/'docs/research/rule-learning-audit-20261104/inventory.json');inv={x['cp']:x for x in inv if x['run']=='run-E'}
texts={cp:(R/x['path']).read_text(encoding='utf-8') for cp,x in inv.items()}
ind=read(O/'frozen-independent-labels.json'); files=sorted((G/'grade/run-E').glob('seg-*/labels.json')); raw={}; loc={}
for p in files:
 for i,x in enumerate(read(p)):
  assert x['cp'] not in raw
  raw[x['cp']]=x;loc[x['cp']]=dict(path=str(p.relative_to(R)).replace('\\','/'),json_pointer=f'/{i}/labels')
key=read(G/'grade/key.json')['E'];pub=read(G/'curves-combined.json')[key['run']]['checkpoints'];assert [x['cp'] for x in pub]==list(range(65)) and sorted(raw)==list(range(65))
origins={}
for cp in range(65):
 n=cp
 while 'unchanged since the previous checkpoint' in texts[n].split('## Thinking written')[0]:n-=1
 origins[cp]=n

def classify(cp,r,field,old,new):
 if r=='M1':
  if cp in range(5,33):return 'clear_error','Full correct includes no useful action button, while the current notebook explicitly adopts ACTION5/6 as context-locked. Four directions alone are only part of this compound rule.','partial; correct only under a narrower controls-only rubric'
  return 'rubric_issue','Four directions are explicit; absence of a useful action-button belief is not itself an explicit no-action-button belief. Essential-content threshold determines correct versus partial.','partial (strict compound rule); correct (directions treated as essential)'
 if r=='M3':
  if field=='source':return 'rubric_issue','Combined collision belief persists, but current notebook only partly states it. Both versus thinking depends on whether source requires independently sufficient evidence. Historical full evidence also originates in an older notebook, not thinking.','both for complementary support; thinking under current-notebook-sufficiency convention; rubric needs historical-notebook source'
  if old=='correct':return 'ambiguity','Notebook says free cell in controls but detailed push algorithm only requires on-board/unwalled destination; multi-box behavior is explicitly untested. Whether free entails crate-crate blocking is ambiguous.','partial; correct if free means unoccupied by any crate'
  if cp>=57:return 'clear_error','Current notebook explicitly rejects box movement off-board: a substantial part of M3, so absent overlooks stated evidence.','partial; correct only if generic free also establishes crate-crate blocking'
  return 'ambiguity','Current notebook boundary/corner dead-box reasoning can imply off-grid refusal, but no explicit general crate-crate rule. Absent versus partial turns on credit for operational consequences.','partial (boundary inference); absent (explicit collision rule required)'
 if r=='M5':return 'ambiguity','Exact local open edges through checker support some grey passage, not a general bridge rule. Decorative/no effect rejects a special role without necessarily predicting blocked grey passage. Partial, absent, and wrong depend on scope and object mapping; do not call every difference an error.','partial (specific passage cases); absent (no adopted bridge belief); wrong only if no effect denies the bridge function'
 if r=='M4':return 'ambiguity','Refused white-to-dark step is explicitly recognized but explained as an edge wall. Rubric permits partial for a right effect with wrong cause; a single observation may instead be below the belief threshold.','partial (adopted local refusal); absent (observation only)'
 if r=='M6':return 'ambiguity','Refused push is adopted and explained by a hidden wall. Partial is supported by wrong-cause clause, but floor-specific scope is inferred from coordinates rather than stated by player.','partial (observable effect); absent (no floor-related belief)'
 if r=='M7' and 14<=cp<=29:return 'clear_error','Earlier accepted cross-colour crate moves persist. Wrong at cp14-20 discards substantial correct cases; absent after retracting dark-to-blue restriction at cp21 discards them again. Retraction replaces that restriction with per-edge walls, not no crate belief.','partial; wrong only if later restriction is judged to revoke all correct cases; absent only if retraction erases all crate-colour knowledge'
 return 'ambiguity','Accepted box-on-white after cross-colour movement supports one case, but may be read as an observation rather than a belief about unrestricted destinations.','partial (one case); absent (no generalized colour belief)'
allrows=[];diffs=[];groups=collections.defaultdict(list);lastnotes={}
for row in ind:
 cp=row['cp']; notebook_cp=origins[cp]; nt=texts[notebook_cp].split('## Thinking written')[0]; nlines=nt.splitlines()
 for r,v in row['labels'].items():
  ov=raw[cp]['labels'][r]
  if ov.get('note'):lastnotes[r]=dict(cp=cp,note=ov['note'],location=loc[cp])
  pv={fld:pub[cp][fld][r] for fld in ['belief','notebook','source']}
  assert all(pv[k]==ov[k] for k in pv)
  support=[]
  patterns={'M1':['ACTION5','ACTION1','ACTION8'],'M3':['off-board','off-grid','free','dead','DEAD','Multi','multi','corner'],'M5':['checker','Checker','OPEN','open edges'],'M7':['Box:','box on','box pushes','WALLS']}.get(r,['wall','WALL','box'])
  for i,line in enumerate(nlines,1):
   if any(p in line for p in patterns):support.append(dict(cp=notebook_cp,path=inv[notebook_cp]['path'],line=i,quote=line,kind='N'))
  entry=dict(cp=cp,rule=r,independent={k:v[k] for k in pv},original_raw={k:ov[k] for k in pv},published=pv,raw_location=dict(**loc[cp],rule=r),published_location=dict(path=str((G/'curves-combined.json').relative_to(R)).replace('\\','/'),run=key['run'],checkpoint_index=cp,rule=r),independent_evidence=v.get('evidence'),supporting_evidence=v.get('supporting_evidence',[]),current_notebook=dict(cp=notebook_cp,path=inv[notebook_cp]['path'],start_line=3,end_line=len(nlines),selected_exact_lines=support),original_latest_note=lastnotes.get(r),independent_rationale=row['rationale'])
  entry['differences']=[]
  for field in pv:
   if v[field]!=ov[field]:
    cat,reason,alt=classify(cp,r,field,ov[field],v[field]);d=dict(field=field,independent=v[field],raw=ov[field],published=pv[field],classification=cat,reason=reason,alternatives=alt)
    entry['differences'].append(d);groups[(r,field,ov[field],v[field],cat)].append(cp)
  allrows.append(entry)
  if entry['differences']:diffs.append(entry)
write('comparison-all-520.json',allrows);write('differences.json',diffs)
counts=collections.Counter(d['field'] for x in diffs for d in x['differences']);classes=collections.Counter(d['classification'] for x in diffs for d in x['differences'])
write('comparison-summary.json',dict(slots=520,fields_checked_per_baseline=1560,raw_published_identical=True,published_corrections=[],differing_slots=len(diffs),differing_fields=dict(counts),classification_field_counts=dict(classes),groups=[dict(rule=k[0],field=k[1],original=k[2],independent=k[3],classification=k[4],checkpoints=v) for k,v in groups.items()]))
write('post-comparison-adjudication.json',dict(frozen_labels_unchanged=True,scope='Interpretation only; no replacement grade set',cautions=[dict(rule='M3',issue='Frozen source thinking can conceal persistence from an older notebook (cp5 line15). The rubric has no separate carried-notebook source. Use explicit origin metadata; do not claim all M3 support was thinking.',alternative='both or explicit historical-notebook source'),dict(rule='M5',issue='Frozen partial credits coordinate-specific checker passage. General bridge rule never adopted; absent remains defensible. Published README suggests absent but published JSON still says wrong.',alternative='absent under general-rule threshold'),dict(rule='M1',issue='Later not available wording may operationally establish no useful action button even though frozen audit demanded more explicit closure.',alternative='correct for later checkpoints under behavioral essential-content interpretation')]))
compfiles=files+[G/'grade/key.json',G/'curves-combined.json',G/'curves.json',G/'README.md']
write('comparison-validation.json',dict(completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),freeze_timestamp=f['frozen_at_utc'],coverage_slots=520,raw_checkpoint_count=len(raw),published_checkpoint_count=len(pub),fields_compared_each=1560,raw_vs_published_field_differences=0,frozen_hash_unchanged=sha(O/'frozen-independent-labels.json')==f['files']['frozen-independent-labels.json'],independent_hash_unchanged=sha(O/'independent-labels.json')==f['files']['independent-labels.json'],comparison_inputs=[dict(path=str(p.relative_to(R)).replace('\\','/'),sha256=sha(p)) for p in compfiles],output_hashes={n:sha(O/n) for n in ['comparison-all-520.json','differences.json','comparison-summary.json','post-comparison-adjudication.json']},errors=[]))
write('progress.json',dict(completed=65,total=65,next_cp=None,comparison_opened=True,frozen=True,comparison_complete=True))
print(json.dumps(dict(differing_slots=len(diffs),fields=dict(counts),classifications=dict(classes))))
