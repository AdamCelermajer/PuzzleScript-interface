import pathlib,json,hashlib,shutil
p=pathlib.Path(__file__).parent
files={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file()}
(p/'final-prior-output-hashes.json').write_text(json.dumps(files,indent=2))
for n in ['independent-labels.json','progress.json','current-belief-handoff.md','README.md','validation.json']: shutil.copyfile(p/n,p/('before-60-'+n))
from audit import save
rows=json.loads((p/'independent-labels.json').read_text())
save(60,[(x['belief'],x['notebook'],x['source']) for x in rows[-1]['labels'].values()],rationale='Read full notebook and thinking. Editing length only; hidden walls still explicitly govern both player and box. Push-only, one-cell pushing and automatic advance remain explicit. No colour restriction/bridge discovery. M3 collision knowledge persists; notebook lacks crate-crate refusal. All labels persist.')
