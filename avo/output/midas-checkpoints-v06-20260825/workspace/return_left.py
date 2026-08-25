import json,subprocess,sys

def run(*a):
 p=subprocess.run([sys.executable,'avo_tool.py',*a],capture_output=True,text=True);print(p.stderr,end='')
 if p.returncode:return None
 return json.loads(p.stdout)
def pos(o):
 g=o['payload']['frame'][-1]
 return next(((x,y,v)for y,r in enumerate(g)for x,v in enumerate(r)if v in(2,6,8,9,11)),None)
o=run('observe')['observation'];last=pos(o);base=o['progress']['levels_completed'];a='ACTION3'
for i in range(25):
 r=run('probe',a,'--rationale','Return orange toward the left-side figure; jump whenever colored terrain blocks horizontal motion.')
 if not r:break
 o=r['transition']['after'];p=pos(o);print(i+1,a,last,'->',p,o['progress']);
 if o['progress']['levels_completed']>base:break
 if a=='ACTION3' and p==last:a='ACTION1'
 else:a='ACTION3'
 last=p
