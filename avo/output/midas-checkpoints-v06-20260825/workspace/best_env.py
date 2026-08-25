import heapq, itertools, json, subprocess, sys
PY=sys.executable; ACTS=['ACTION4','ACTION1','ACTION2']
def run(*a):
 p=subprocess.run([PY,'avo_tool.py',*a],capture_output=True,text=True)
 if p.returncode: raise RuntimeError((p.stdout+p.stderr).strip())
 return json.loads(p.stdout)
def obs():return run('observe')['observation']
def grid(o):return o['payload']['frame'][-1]
def key(o):return (o['progress']['levels_completed'],tuple(map(tuple,grid(o))))
def pos(o):return next(((x,y,v) for y,r in enumerate(grid(o)) for x,v in enumerate(r) if v in (2,6,8)),(-99,-99,-1))
rootcp=sys.argv[1]; limit=int(sys.argv[2]); run('restore',rootcp); root=obs(); base=root['progress']['levels_completed']
serial=itertools.count(); H=[]
def push(cp,o,path):
 x,y,v=pos(o); heapq.heappush(H,(-x,len(path),next(serial),cp,o,path))
push(rootcp,root,[]); seen={key(root)}; n=0
while H and n<limit:
 _,_,_,cp,o,path=heapq.heappop(H); px=pos(o)[0]
 for a in ACTS:
  run('restore',cp); r=run('probe',a,'--rationale','Forward-only best-first checkpoint search over right, jump, and descend actions.')
  n+=1; no=r['transition']['after']; p=pos(no); prog=no['progress']['levels_completed']; k=key(no)
  if prog>base:
   print('FOUND',prog,n,path+[a],p,flush=True);open('best_solution.txt','w').write('\n'.join(path+[a]));raise SystemExit
  if k in seen or p[0]<px: continue
  seen.add(k); c=run('checkpoint','--label',f'best_d{len(path)+1}_x{p[0]}_n{len(seen)}')['checkpoint_id'];push(c,no,path+[a])
 if n%30<3: print('n',n,'seen',len(seen),'heap',len(H),'at',pos(o),'depth',len(path),'bestx',-H[0][0] if H else None,flush=True)
print('NO',n,len(seen),len(H))
