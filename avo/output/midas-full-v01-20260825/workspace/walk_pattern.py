import json, subprocess, sys
pat=sys.argv[1].split(','); n=int(sys.argv[2])
for i in range(n):
 a=pat[i%len(pat)]
 p=subprocess.run([sys.executable,'avo_tool.py','probe',a,'--rationale','Last-budget systematic movement pattern to seek a new reachable state.'],capture_output=True,text=True)
 if p.returncode: print(p.stdout,p.stderr); break
 d=json.loads(p.stdout); tr=d['transition']; o=tr['after']; b=o['payload']['frame'][-1]
 pos=[(y,x,v) for y,r in enumerate(b) for x,v in enumerate(r) if v in (2,3,7)]
 print(tr['sequence'],a,o['progress'],pos,flush=True)
 if d.get('task',{}).get('terminal'): break
