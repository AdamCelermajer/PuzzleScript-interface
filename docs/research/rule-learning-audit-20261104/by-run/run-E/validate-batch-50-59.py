"""Validate the bounded independent continuation; never load original labels."""
import collections
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
RULES = [f'M{i}' for i in range(1, 9)]
INV = {x['cp']: x for x in json.loads((ROOT / 'docs/research/rule-learning-audit-20261104/inventory.json').read_text(encoding='utf-8')) if x['run'] == 'run-E'}
rows = json.loads((OUT / 'independent-labels.json').read_text(encoding='utf-8'))
errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


check([r['cp'] for r in rows] == list(range(60)), 'Expected exactly cp0-59 in order')
before = json.loads((OUT / 'before-50-independent-labels.json').read_text(encoding='utf-8'))
prefix_preserved = rows[:50] == before and len(before) == 50
check(prefix_preserved, 'Prior 400 judgments changed')
texts = {}
source_checks = {}


def source(cp):
    if cp not in texts:
        entry = INV[cp]
        data = (ROOT / entry['path']).read_bytes()
        sha = digest(data)
        ok = sha == entry['sha256'] and len(data) == entry['bytes']
        check(ok, f'cp{cp}: inventory hash/size mismatch')
        source_checks[cp] = dict(cp=cp, path=entry['path'], bytes=len(data), sha256=sha, inventory_sha256_matches=sha == entry['sha256'], inventory_bytes_match=len(data) == entry['bytes'])
        texts[cp] = data.decode('utf-8')
    return texts[cp]


def evidence(ev, cp, rule):
    origin = ev['cp']
    check(origin <= cp, f'cp{cp} {rule}: future evidence')
    check(ev['path'] == INV[origin]['path'], f'cp{cp} {rule}: wrong path')
    lines = source(origin).splitlines()
    line = ev['line']
    check(1 <= line <= len(lines) and ev['quote'] in lines[line - 1], f'cp{cp} {rule}: quote/line mismatch')
    heading = next(i for i, s in enumerate(lines, 1) if s.startswith('## Thinking written'))
    check(ev['kind'] == ('N' if line < heading else 'T'), f'cp{cp} {rule}: wrong notebook/thinking section')


counts = collections.Counter()
quotes = batch_quotes = supporting = notes = changes = 0
max_words = 0
notebook_origins = {}
for row in rows:
    cp = row['cp']
    check(list(row['labels']) == RULES, f'cp{cp}: rule coverage/order')
    check(INV[cp]['rules'] == RULES, f'cp{cp}: inventory rule coverage mismatch')
    check(row.get('full_read') is True, f'cp{cp}: missing full-read attestation')
    for rule, label in row['labels'].items():
        for field in ['belief', 'notebook']:
            check(label[field] in {'absent', 'wrong', 'partial', 'correct'}, f'cp{cp} {rule}: invalid {field}')
        check(label['source'] in {'none', 'notebook', 'thinking', 'both'}, f'cp{cp} {rule}: invalid source')
        check((label['belief'] == 'absent') == (label['source'] == 'none'), f'cp{cp} {rule}: absent/source mismatch')
        counts[label['belief']] += 1
        if label['belief'] != 'absent':
            evidence(label['evidence'], cp, rule)
            quotes += 1
            batch_quotes += cp >= 50
        for ev in label.get('supporting_evidence', []):
            evidence(ev, cp, rule)
            supporting += cp >= 50
        if cp >= 50:
            changed = label['belief'] != rows[cp - 1]['labels'][rule]['belief']
            changes += changed
            check(not changed or bool(label.get('note')), f'cp{cp} {rule}: changed belief lacks note')
            if label.get('note'):
                note = label['note']
                ev = label['evidence']
                check(note == ev['kind'] + ': ' + ev['quote'], f'cp{cp} {rule}: note differs from evidence')
                words = len(ev['quote'].split())
                check(words <= 20, f'cp{cp} {rule}: note over 20 words')
                max_words = max(max_words, words)
                notes += 1
    if cp >= 50:
        source(cp)
        origin = cp
        while '(unchanged since the previous checkpoint' in source(origin).split('## Thinking written')[0]:
            origin -= 1
        notebook_origins[cp] = origin

prior_hashes = json.loads((OUT / 'batch-50-59-prior-output-hashes.json').read_text(encoding='utf-8'))
preservation_checks = {}
for name, sha in prior_hashes.items():
    preserved = OUT / ('before-50-' + name) if name in {'independent-labels.json','progress.json','current-belief-handoff.md','validation.json'} else OUT / name
    ok = preserved.exists() and digest(preserved.read_bytes()) == sha
    preservation_checks[name] = ok
    check(ok, f'Previous output not preserved: {name}')

progress = json.loads((OUT / 'progress.json').read_text(encoding='utf-8'))
check(progress == dict(completed=60, total=65, next_cp=60, comparison_opened=False), 'Progress mismatch')
schema = json.loads((OUT / 'batch-50-59-schema-check.json').read_text(encoding='utf-8'))
check(schema['exit_code'] == 0 and schema['stdout'].strip() == 'ok: 10 checkpoints x 8 rules', 'Repository checker did not pass')
fixture = OUT / 'batch-50-59-check'
projected = json.loads((fixture / 'labels.json').read_text(encoding='utf-8'))
check([r['cp'] for r in projected] == list(range(50,60)), 'Checker projection coverage mismatch')
for row in projected:
    cp = row['cp']
    check(digest((fixture / f'cp-{cp:03d}.md').read_bytes()) == INV[cp]['sha256'], f'cp{cp}: checker input copy mismatch')
    for rule in RULES:
        check(all(row['labels'][rule][k] == rows[cp]['labels'][rule][k] for k in ['belief','notebook','source']), f'cp{cp} {rule}: checker label projection mismatch')
metadata_checks = []
reference_rules = json.loads((fixture / 'rules.json').read_text(encoding='utf-8'))
for rel in ['docs/research/rule-learning-audit-20261104/inventory.json', 'docs/research/rule-learning-20261028/grade/INSTRUCTIONS.md', 'docs/research/rule-learning-20261028/grade/check.py'] + [f'docs/research/rule-learning-20261028/grade/run-E/seg-{seg}/rules.json' for seg in [4,5,6]]:
    data = (ROOT / rel).read_bytes()
    metadata_checks.append(dict(path=rel, bytes=len(data), sha256=digest(data)))
    if rel.endswith('/rules.json'):
        check(json.loads(data) == reference_rules, f'Rule definitions differ: {rel}')
report = dict(
    status='INCOMPLETE_NOT_FROZEN', checkpoints_reviewed=60, checkpoints_expected=65,
    slots_reviewed=480, slots_expected=520, missing_checkpoints=list(range(60,65)),
    quote_matches=quotes, counts=dict(counts), comparison_performed=False,
    unreviewed_slots_labeled_absent=False,
    bounded_batch=dict(first_cp=50,last_cp=59,checkpoints=10,new_judgments=80,
        quote_matches=batch_quotes,supporting_quote_matches=supporting,
        new_notes_checked=notes,new_notes_max_words=max_words,combined_label_changes=changes,
        prior_400_judgments_unchanged=prefix_preserved,prior_outputs_preserved=preservation_checks,
        repository_checker=dict(exit_code=schema['exit_code'],result=schema['stdout'].strip(),projection='batch-50-59-check'),
        notebook_origin_by_checkpoint=notebook_origins,
        rubric_inventory_checker_rule_hashes=metadata_checks,
        source_inventory_checks=[dict(source_checks[cp],full_read=rows[cp]['full_read'],rules_covered=list(rows[cp]['labels'])) for cp in range(50,60)],
        additional_evidence_and_notebook_source_checks=[source_checks[cp] for cp in sorted(source_checks) if cp < 50]),
    errors=errors)
(OUT / 'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(OUT / 'batch-50-59-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','checkpoints_reviewed','slots_reviewed','quote_matches','counts','errors']},indent=2))
print(f'Batch: {batch_quotes} primary + {supporting} supporting citations; {notes} notes; max {max_words} words; {changes} combined changes.')
print(f'Input hashes checked: {len(source_checks)}; notebook origins: {notebook_origins}')
raise SystemExit(bool(errors))
