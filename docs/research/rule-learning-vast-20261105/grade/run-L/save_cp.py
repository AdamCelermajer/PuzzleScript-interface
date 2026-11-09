import json,sys,pathlib
root=pathlib.Path(__file__).parent
seg=int(sys.argv[1]); cp=int(sys.argv[2]); patches=json.loads(sys.stdin.read() or '{}')
p=root/f'seg-{seg}'/'labels.json'
a=json.loads(p.read_text()) if p.exists() else []
prev=a[-1]['labels'] if a else json.loads((p.parent/'start.json').read_text())
v={r:{k:x for k,x in z.items() if k!='note'} for r,z in prev.items()}
for r,z in patches.items(): v[r].update(z)
a.append({'cp':cp,'labels':v}); p.write_text(json.dumps(a,indent=2)+'\n',encoding='utf-8')

