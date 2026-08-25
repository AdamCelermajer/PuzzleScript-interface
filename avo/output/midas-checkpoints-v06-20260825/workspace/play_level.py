import json, subprocess, sys

def call(*args):
    p=subprocess.run([sys.executable,'avo_tool.py',*args],capture_output=True,text=True)
    if p.returncode:
        print(p.stdout); print(p.stderr); raise SystemExit(p.returncode)
    return json.loads(p.stdout)

def pos(obs):
    g=obs['payload']['frame'][-1]
    for y,r in enumerate(g):
        for x,v in enumerate(r):
            if v in (2,6,8): return (x,y,v)
    return None

o=call('observe')['observation']
base=o['progress']['levels_completed']
last=pos(o)
print('start',base,last)
action='ACTION4'
for i in range(int(sys.argv[1]) if len(sys.argv)>1 else 50):
    r=call('probe',action,'--rationale','Systematic platform traversal: move toward the goal; when horizontal motion is blocked, jump from generated support.')
    o=r['transition']['after']; p=pos(o); prog=o['progress']['levels_completed']
    print(i+1,action,last,'->',p,'progress',prog)
    if prog>base: break
    if action=='ACTION4' and p==last:
        action='ACTION1'
    else:
        action='ACTION4'
    last=p
