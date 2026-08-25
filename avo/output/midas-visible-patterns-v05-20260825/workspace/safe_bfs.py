import json,subprocess,sys
from collections import deque
A=['ACTION1','ACTION2','ACTION3','ACTION4']
def run(cmd):
 p=subprocess.run([sys.executable,'avo_tool.py']+cmd,text=True,capture_output=True)
 if p.returncode:return None
 return json.loads(p.stdout)
def evalp(path):
 run(['reset','--reason','Bounded breadth-first test for a safe approach state without recoloring the NPC.'])
 last=None
 for a in path:
  j=run(['probe',a,'--rationale','Breadth-first directional transition test from a controlled fresh level state.'])
  if not j:return None,None
  last=j['transition']['after']
  if last['progress']['levels_completed']>4:
   print('SOLVED',path,flush=True);raise SystemExit
 g=last['payload']['frame'][-1]
 return tuple(map(tuple,g)),g
q=deque([()]);seen=set();n=0
while q and n<45:
 p=q.popleft()
 if len(p)>=7:continue
 for a in A:
  c=p+(a,); k,g=evalp(c);n+=1
  if k is None:continue
  # NPC recolored is an unsafe absorbing branch for this search.
  if any(10 in r for r in g):continue
  if k in seen:continue
  seen.add(k)
  pos=[(r,x) for r,row in enumerate(g) for x,v in enumerate(row) if v in (2,6,9)]
  print(n,len(c),''.join(x[-1] for x in c),pos,flush=True)
  q.append(c)
  if n>=45:break
print('done',n,'frontier',len(q))
