"""Run-F audit validation; writes only inside this audit folder."""
from pathlib import Path
import json,hashlib,runpy,sys,io,contextlib
from unittest.mock import patch
from collections import Counter
ROOT=Path(__file__).resolve().parents[5]
OUT=Path(__file__).resolve().parent
inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
labels=json.loads((OUT/'labels.json').read_text(encoding='utf-8'))
rules=json.loads((OUT/'rules.json').read_text())
errors=[]
assert [x['cp'] for x in inv]==list(range(32))
if [x['cp'] for x in labels]!=[x['cp'] for x in inv]:errors.append('Checkpoint coverage/order mismatch')
texts={x['cp']:(ROOT/x['path']).read_text(encoding='utf-8') for x in inv}
quote_count=0
for row in labels:
 cp=row['cp']
 if set(row['labels'])!=set(inv[cp]['rules']):errors.append(f'{cp}: rule coverage')
 if not row['full_read']:errors.append(f'{cp}: not fully read')
 if hashlib.sha256((ROOT/inv[cp]['path']).read_bytes()).hexdigest()!=inv[cp]['sha256']:errors.append(f'{cp}: input hash changed')
 for rid,v in row['labels'].items():
  if v['belief'] not in {'correct','partial','wrong','absent'} or v['notebook'] not in {'correct','partial','wrong','absent'}:errors.append(f'{cp} {rid}: invalid grade')
  if v['source'] not in {'notebook','thinking','both','none'}:errors.append(f'{cp} {rid}: invalid source')
  if (v['belief']=='absent')!=(v['source']=='none'):errors.append(f'{cp} {rid}: absent/source mismatch')
  note=v.get('note','')
  if note and (note[:3] not in {'N: ','T: '} or len(note[3:].split())>20):errors.append(f'{cp} {rid}: note format/length {len(note[3:].split())}')
  changed=cp==0 or v['belief']!=labels[cp-1]['labels'][rid]['belief']
  if changed and v['belief']!='absent' and not note:errors.append(f'{cp} {rid}: missing change quote')
  if v['belief']=='absent' and not v.get('absence_rationale'):errors.append(f'{cp} {rid}: unsupported absence')
  if v['belief']!='absent' and not v['evidence']:errors.append(f'{cp} {rid}: missing evidence')
  if cp and not changed and v.get('persisted_from_cp')!=cp-1:errors.append(f'{cp} {rid}: missing persistence link')
  for e in v['evidence']:
   quote_count+=1;s=texts[e['cp']];q=e['quote'];line=e['line']
   if e['cp']>cp:errors.append(f'{cp} {rid}: future evidence')
   if q not in s or q not in s.splitlines()[line-1]:errors.append(f'{cp} {rid}: quote/line mismatch')
   if e['path']!=inv[e['cp']]['path']:errors.append(f'{cp} {rid}: evidence path mismatch')
   part=s.split('## Thinking',1)[0] if e['section']=='notebook' else s.split('## Thinking',1)[1]
   if q not in part:errors.append(f'{cp} {rid}: evidence section mismatch')
  if note and not any(e['quote']==note[3:] and e['section']==('notebook' if note[0]=='N' else 'thinking') for e in v['evidence']):errors.append(f'{cp} {rid}: note quote missing in cited evidence')
# Execute unchanged official checker, supplying inventoried original cp paths instead
# of duplicating source checkpoints into the audit directory. No start.json is read.
old_argv=sys.argv[:];sys.argv=[str(ROOT/'docs/research/rule-learning-20261028/grade/check.py'),str(OUT)]
buf=io.StringIO()
with patch('glob.glob',return_value=[str(ROOT/x['path']) for x in inv]),contextlib.redirect_stdout(buf):
 runpy.run_path(sys.argv[0],run_name='__main__')
sys.argv=old_argv
official=buf.getvalue().strip()
if official!='ok: 32 checkpoints x 7 rules':errors.append('Official checker: '+official)
report={'checkpoints':len(labels),'rules_per_checkpoint':len(rules),'rule_slots':sum(len(x['labels']) for x in labels),'exact_quote_references_checked':quote_count,'input_hashes_checked':len(inv),'original_checker':official,'belief_counts':dict(Counter(v['belief'] for r in labels for v in r['labels'].values())),'notebook_counts':dict(Counter(v['notebook'] for r in labels for v in r['labels'].values())),'source_counts':dict(Counter(v['source'] for r in labels for v in r['labels'].values())),'unreviewed_slots':0,'errors':errors}
if (OUT/'freeze.json').exists():
 f=json.loads((OUT/'freeze.json').read_text());report['frozen_labels_hash_matches']=hashlib.sha256((OUT/'labels.json').read_bytes()).hexdigest()==f['labels_sha256']
 if not report['frozen_labels_hash_matches']:errors.append('Frozen labels hash mismatch')
if (OUT/'comparison.json').exists():
 comparison=json.loads((OUT/'comparison.json').read_text(encoding='utf-8'))
 comparison_quotes=0
 for target,rows in comparison['disagreements'].items():
  for row in rows:
   for e in row['evidence']:
    comparison_quotes+=1
    if e['quote'] not in texts[e['cp']].splitlines()[e['line']-1]:errors.append('Comparison quote mismatch')
 report['comparison_quote_references_checked']=comparison_quotes
 report['read_only_comparison_inputs_unchanged']=all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==h for path,h in comparison['read_only_inputs_sha256'].items())
 if not report['read_only_comparison_inputs_unchanged']:errors.append('Comparison input changed')
 if comparison['labels_sha256']!=hashlib.sha256((OUT/'labels.json').read_bytes()).hexdigest():errors.append('Comparison uses wrong frozen hash')
 if (OUT/'freeze.json').exists():
  report['frozen_evidence_hashes_match']=all(hashlib.sha256((OUT/n).read_bytes()).hexdigest()==h for n,h in f['other_frozen_evidence'].items())
  if not report['frozen_evidence_hashes_match']:errors.append('Frozen evidence changed')
(OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));sys.exit(bool(errors))
