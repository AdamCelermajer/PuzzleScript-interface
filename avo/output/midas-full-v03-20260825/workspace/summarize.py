import subprocess,json
s=subprocess.check_output(['python','avo_tool.py','history'],text=True); j=json.loads(s[s.find('{'):])
for t in j['transitions']:
 if t['sequence']<33: continue
 def last(o): return o['payload']['frame'][-1]
 def coords(g): return [(v,r,c) for r,row in enumerate(g) for c,v in enumerate(row) if v not in (0,1,4,5,6)]
 b=last(t['before']);a=last(t['after']); dif=[]
 if len(b)==len(a) and len(b[0])==len(a[0]): dif=[(r,c,b[r][c],a[r][c]) for r in range(len(a)) for c in range(len(a[0])) if b[r][c]!=a[r][c]]
 print(t['sequence'],t['action']['id'],coords(b),'->',coords(a),'diff',dif,'p',t['after']['progress']['levels_completed'])
