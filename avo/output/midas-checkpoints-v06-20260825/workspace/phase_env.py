import heapq,itertools,json,subprocess,sys
PY=sys.executable
def run(*a):
 p=subprocess.run([PY,'avo_tool.py',*a],capture_output=True,text=True)
 if p.returncode: raise RuntimeError((p.stdout+p.stderr).strip())
 return json.loads(p.stdout)
def obs():return run('observe')['observation']
def grid(o):return o['payload']['frame'][-1]
def key(o):return (o['progress']['levels_completed'],tuple(map(tuple,grid(o))))
def pos(o):return next(((x,y,v) for y,r in enumerate(grid(o)) for x,v in enumerate(r) if v in (2,6,8,9,11)),(-99,-99,-1))
rootcp=sys.argv[1];limit=int(sys.argv[2]);run('restore',rootcp);root=obs();base=root['progress']['levels_completed']
S=itertools.count();H=[]
def pri(o,path):
 x,y,v=pos(o); orange=v in (9,11); return (0 if orange else 1, x if orange else -x, len(path),next(S))
def push(cp,o,path):heapq.heappush(H,(*pri(o,path),cp,o,path))
push(rootcp,root,[]);seen={key(root)};n=0
while H and n<limit:
 *_,cp,o,path=heapq.heappop(H);x,y,v=pos(o);orange=v in(9,11);acts=(['ACTION3','ACTION1','ACTION2'] if orange else ['ACTION4','ACTION1','ACTION2'])
 for a in acts:
  run('restore',cp);r=run('probe',a,'--rationale','Phase-aware reversible search: move blue toward orange, then move orange back toward the unpainted figure, with jumps and descents.')
  n+=1;no=r['transition']['after'];nx,ny,nv=pos(no);prog=no['progress']['levels_completed'];k=key(no);norange=nv in(9,11)
  if prog>base:
   print('FOUND',prog,n,path+[a],(nx,ny,nv),flush=True);open('phase_solution.txt','w').write('\n'.join(path+[a]));raise SystemExit
  if k in seen:continue
  if orange==norange and ((not orange and nx<x) or (orange and nx>x)):continue
  seen.add(k);c=run('checkpoint','--label',f'phase_d{len(path)+1}_x{nx}_n{len(seen)}')['checkpoint_id'];push(c,no,path+[a])
 if n%30<3:print('n',n,'seen',len(seen),'heap',len(H),'at',(x,y,v),'depth',len(path),flush=True)
print('NO',n,len(seen),len(H))
