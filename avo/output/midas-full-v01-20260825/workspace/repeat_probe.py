import json, subprocess, sys
a=sys.argv[1]; n=int(sys.argv[2])
for i in range(n):
 p=subprocess.run([sys.executable,'avo_tool.py','probe',a,'--rationale','Repeated controlled traversal or undo.'],capture_output=True,text=True)
 if p.returncode: print(p.stdout,p.stderr);break
 d=json.loads(p.stdout); o=d['transition']['after']; b=o['payload']['frame'][-1]
 pos=[(y,x,v) for y,r in enumerate(b) for x,v in enumerate(r) if v in (2,3,7)]
 print(d['transition']['sequence'],o['progress']['levels_completed'],pos,flush=True)
 if d.get('task',{}).get('terminal'): break
