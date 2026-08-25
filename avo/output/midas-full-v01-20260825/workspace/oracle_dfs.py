import json, subprocess, sys, hashlib

ACTIONS = ["ACTION3", "ACTION1", "ACTION4", "ACTION2"]
limit = int(sys.argv[1]) if len(sys.argv)>1 else 16
max_probes = int(sys.argv[2]) if len(sys.argv)>2 else 300
probes = 0

def call(action=None):
    global probes
    cmd=[sys.executable,"avo_tool.py"]
    if action is None:
        cmd += ["observe"]
    else:
        cmd += ["probe",action,"--rationale","Systematic reversible search for a winning transition."]
        probes += 1
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode:
        print(p.stdout,p.stderr); raise SystemExit(p.returncode)
    d=json.loads(p.stdout)
    o=d["observation"] if action is None else d["transition"]["after"]
    return d,o

def state(o):
    fs=o.get("payload",{}).get("frame",[])
    b=fs[-1] if fs else []
    return (json.dumps(b,separators=(",",":")), o.get("progress",{}).get("levels_completed",-1))

d,root_o=call()
root_progress=state(root_o)[1]
visited={state(root_o):0}
path=[]

def dfs(o, depth):
    global probes
    if depth >= limit or probes >= max_probes:
        return False
    parent=state(o)
    for a in ACTIONS:
        if probes >= max_probes: return False
        d,n=call(a); ns=state(n); path.append(a)
        print(f"probe={probes} depth={depth+1} {a} progress={ns[1]} path={' '.join(path)}", flush=True)
        if d.get("task",{}).get("terminal") or ns[1] > root_progress:
            print("FOUND", " ".join(path), flush=True)
            return True
        old=visited.get(ns)
        if ns != parent and (old is None or old > depth+1):
            visited[ns]=depth+1
            if dfs(n,depth+1): return True
        # Undo exactly this probe and verify restoration.
        d,u=call("ACTION7"); us=state(u)
        if us != parent:
            print("UNDO_MISMATCH", depth, a, "expected", hashlib.md5(parent[0].encode()).hexdigest(),
                  "got", hashlib.md5(us[0].encode()).hexdigest(), flush=True)
            raise SystemExit(3)
        path.pop()
    return False

ok=dfs(root_o,0)
print(json.dumps({"found":ok,"probes":probes,"visited":len(visited),"path":path}))
