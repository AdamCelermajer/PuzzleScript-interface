import json,hashlib,collections,re
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[4]
f=json.loads((O/'freeze.json').read_text());s=json.loads((O/'comparison-summary.json').read_text());d=json.loads((O/'disagreements.json').read_text(encoding='utf-8'));m=json.loads((O/'reading-manifest.json').read_text());a=json.loads((O/'labels.json').read_text());e=json.loads((O/'independent-labels.json').read_text(encoding='utf-8'))
for n,h in f['files'].items():assert hashlib.sha256((O/n).read_bytes()).hexdigest()==h,n
for x in m:assert hashlib.sha256((R/x['path']).read_bytes()).hexdigest()==x['sha256']
for n,h in s['inputs_sha256'].items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h,n
assert len(d)==338 and len({(x['target'],x['cp'],x['rule'],x['field']) for x in d})==338
for target in ['raw','published']:
 dd=[x for x in d if x['target']==target]
 assert len(dd)==169 and dict(collections.Counter(x['field'] for x in dd))==s['by_field']
 assert dict(collections.Counter(x['classification'] for x in dd))==s['by_classification_fields']
 for x in dd:assert x['independent']==a[x['cp']]['labels'][x['rule']][x['field']]
for x,y in zip(a,e):assert x['labels']=={k:{f:v[f] for f in ['belief','source','notebook','note']} for k,v in y['labels'].items()}
report=(O/'REPORT.md').read_text(encoding='utf-8');quotes=re.findall('“(.*?)”',report)
alltext='\n'.join((R/x['path']).read_text(encoding='utf-8') for x in m)
for q in quotes:assert q in alltext,q
result=dict(frozen_hashes_unchanged=True,all_33_checkpoint_hashes_unchanged=True,all_comparison_input_hashes_unchanged=True,exact_difference_records=338,per_target_fields=169,report_quotes_validated=len(quotes),all_counts_consistent=True,errors=[])
(O/'final-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
