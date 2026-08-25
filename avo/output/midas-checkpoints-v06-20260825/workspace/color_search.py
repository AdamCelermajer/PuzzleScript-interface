import heapq,itertools,json,subprocess,sys
PY=sys.executable
def run(*a):
 p=subprocess.run([PY,'avo_tool.py',*a],capture_output=True,text=True)
 if p.returncode:raise RuntimeError((p.stdout+p.stderr).strip())
 return json.loads(p.stdout)
def obs():return run('observe')['observation']
def g(o):return o['payload']['frame'][-1]
def key(o):return(o['progress']['levels_completed'],tuple(map(tuple,g(o))))
def pos(o):return next(((x,y,v)for y,r in enumerate(g(o))for x,v in enumerate(r)if v in(2,6,8,9,11)),(-9,-9,-1))
S=itertools.count();H=[]
def score(o,path):
 q=g(o);bs=[(x,y)for y,r in enumerate(q)for x,v in enumerate(r)if v in(4,7,10)];mx=max(x for x,y in bs);x,y,v=pos(o);orange=v in(9,11)
 return(0 if orange else 1,(x if orange else -mx),(-len(bs) if not orange else x),len(path),next(S))
cp=sys.argv[1];limit=int(sys.argv[2]);run('restore',cp);o=obs();base=o['progress']['levels_completed'];heapq.heappush(H,(*score(o,[]),cp,o,[]));seen={key(o)};n=0
while H and n<limit:
 *_,cp,o,path=heapq.heappop(H)
 for a in ['ACTION4','ACTION1','ACTION3','ACTION2']:
  run('restore',cp);r=run('probe',a,'--rationale','Checkpoint best-first search prioritizing colored-path extension while allowing necessary reversals around the central void.')
  n+=1;no=r['transition']['after'];k=key(no);p=pos(no)
  if no['progress']['levels_completed']>base:
   print('FOUND',n,path+[a],p);open('color_solution.txt','w').write('\n'.join(path+[a]));raise SystemExit
  if k in seen:continue
  seen.add(k);c=run('checkpoint','--label',f'color_d{len(path)+1}_n{len(seen)}')['checkpoint_id'];heapq.heappush(H,(*score(no,path+[a]),c,no,path+[a]))
 if n%20<4:print(n,len(seen),len(H),pos(o),len(path),flush=True)
print('NO',n,len(seen),len(H))
