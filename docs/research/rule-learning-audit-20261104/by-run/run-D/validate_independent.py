"""Validate exact inventory, rule, evidence and source coverage without original grades."""
import contextlib
import hashlib
import io
import json
import runpy
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
inv=[x for x in json.loads((ROOT/'docs/research/rule-learning-audit-20261104/inventory.json').read_text()) if x['run']=='run-D']
cp={x['cp']:x for x in inv}
rows=read('independent-labels.json')
evidence=read('evidence.json')
coverage=read('reading-coverage.json')
assert [x['cp'] for x in rows]==[x['cp'] for x in inv]==list(range(25))
assert [x['cp'] for x in coverage]==list(range(25))
assert all(x['review_status']=='full_text_read' for x in coverage)
assert len(evidence)==175
assert {(x['cp'],x['rule']) for x in evidence}=={(x['cp'],r) for x in inv for r in x['rules']}
for x in inv:
    assert hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest()==x['sha256']
for row in rows:
    assert set(row['labels'])==set(cp[row['cp']]['rules'])
    for r,v in row['labels'].items():
        assert v['belief'] in {'correct','partial','wrong','absent'}
        assert v['notebook'] in {'correct','partial','wrong','absent'}
        assert v['source'] in {'notebook','thinking','both','none'}
        assert (v['source']=='none')==(v['belief']=='absent')
        if v['note']:
            assert v['note'][:3] in {'N: ','T: '}
            assert len(v['note'][3:].split())<=20
            assert v['note'][3:] in (ROOT/cp[v['evidence_cp']]['path']).read_text(encoding='utf-8')
quotes=0
for x in evidence:
    assert x['review_status']=='full_text_read'
    assert (x['belief'],x['notebook'],x['source'])==tuple(rows[x['cp']]['labels'][x['rule']][k] for k in ('belief','notebook','source'))
    for q in x['evidence']:
        assert q['cp']<=x['cp']
        assert q['path']==cp[q['cp']]['path']
        lines=(ROOT/q['path']).read_text(encoding='utf-8').splitlines()
        assert q['quote'] in '\n'.join(lines[q['line_start']-1:q['line_end']])
        assert len(q['quote'].split())<=20
        boundary=next(i+1 for i,l in enumerate(lines) if l.startswith('## Thinking written since'))
        assert (q['line_start']<boundary)==(q['origin']=='notebook')
        quotes+=1
for x in read('source-verification.json'):
    p=ROOT/x['path']; assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
    lines=p.read_text(encoding='utf-8').splitlines()
    for q in x['evidence']:assert lines[q['line']-1]==q['quote']

# Run the repository checker unchanged, adapting its file-discovery glob to the
# real, read-only checkpoint paths (no copied checkpoints or original handoffs).
rules=(ROOT/'docs/research/rule-learning-20261028/grade/run-D/seg-0/rules.json').read_bytes()
assert (OUT/'rules.json').read_bytes()==rules
assert (OUT/'labels.json').read_bytes()==(OUT/'independent-labels.json').read_bytes()
buf=io.StringIO()
with patch('sys.argv',['check.py',str(OUT)]),patch('glob.glob',return_value=[str(ROOT/x['path']) for x in inv]),contextlib.redirect_stdout(buf):
    runpy.run_path(str(ROOT/'docs/research/rule-learning-20261028/grade/check.py'),run_name='__main__')
assert buf.getvalue().strip()=='ok: 25 checkpoints x 7 rules',buf.getvalue()
manifest=OUT/'freeze-manifest.json'
if manifest.exists():
    for name,sha in read('freeze-manifest.json')['sha256'].items():
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==sha,(name,'frozen hash mismatch')
result=dict(status='PASS',checkpoints=25,rules=7,slots=175,unreviewed_slots=0,
            quote_references_validated=quotes,checkpoint_hashes_validated=25,
            repository_checker=buf.getvalue().strip(),
            combined_counts=dict(Counter(v['belief'] for x in rows for v in x['labels'].values())),
            notebook_counts=dict(Counter(v['notebook'] for x in rows for v in x['labels'].values())),
            source_counts=dict(Counter(v['source'] for x in rows for v in x['labels'].values())),
            caveat='Quote validation verifies literal support locations, not the semantic judgment; full reading is documented in the progress log.')
(OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
