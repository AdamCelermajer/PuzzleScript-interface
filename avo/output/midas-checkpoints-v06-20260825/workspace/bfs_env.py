import collections, json, subprocess, sys

PY=sys.executable
ACTS=['ACTION4','ACTION1','ACTION3','ACTION2']

def run(*args):
    p=subprocess.run([PY,'avo_tool.py',*args],capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError((p.stdout+'\n'+p.stderr).strip())
    return json.loads(p.stdout)

def obs(): return run('observe')['observation']
def key(o):
    g=o['payload']['frame'][-1]
    return (o['progress']['levels_completed'],tuple(tuple(r) for r in g))
def ppos(o):
    g=o['payload']['frame'][-1]
    return next(((x,y,v) for y,r in enumerate(g) for x,v in enumerate(r) if v in (2,6,8)),None)

root_cp=sys.argv[1]
limit=int(sys.argv[2]) if len(sys.argv)>2 else 250
run('restore',root_cp)
root=obs(); base=root['progress']['levels_completed']
Q=collections.deque([(root_cp,root,[])])
seen={key(root)}; probes=0
print('BFS root',base,ppos(root),flush=True)
while Q and probes<limit:
    cp,o,path=Q.popleft()
    for a in ACTS:
        run('restore',cp)
        try:
            r=run('probe',a,'--rationale','Systematic reversible breadth-first state search from a checkpoint; test one direction and preserve each distinct successor.')
        except RuntimeError as e:
            print('probe error',e,flush=True); raise
        probes+=1
        no=r['transition']['after']; nk=key(no)
        prog=no['progress']['levels_completed']
        if prog>base:
            print('FOUND',prog,'probes',probes,'path',' '.join(path+[a]),'pos',ppos(no),flush=True)
            open('bfs_solution.txt','w').write('\n'.join(path+[a]))
            raise SystemExit(0)
        if nk not in seen:
            seen.add(nk)
            c=run('checkpoint','--label',f'bfs_d{len(path)+1}_n{len(seen)}')['checkpoint_id']
            Q.append((c,no,path+[a]))
    if len(seen)%20<4:
        print('states',len(seen),'queue',len(Q),'probes',probes,'depth',len(path),'pos',ppos(o),flush=True)
print('NOT FOUND','states',len(seen),'queue',len(Q),'probes',probes,flush=True)
raise SystemExit(2)
