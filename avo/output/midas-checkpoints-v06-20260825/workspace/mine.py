import json
D=json.load(open('history.json'))['transitions']
def k(o):return (o['progress']['levels_completed'],tuple(map(tuple,o['payload']['frame'][-1])))
def pos(o):
 g=o['payload']['frame'][-1]
 return next(((x,y,v)for y,r in enumerate(g)for x,v in enumerate(r)if v in(2,6,8,9,11)),None)
Ts=[t for t in D if 768<=t['sequence']<=887]
root=k(Ts[0]['before']);seen={root}; parent={}; cpnum=222; cps={root:'cp_169'}
for t in Ts:
 b=k(t['before']);a=k(t['after'])
 if a not in seen:
  seen.add(a);cpnum+=1;cps[a]=f'cp_{cpnum:03d}';parent[a]=(b,t['action']['id'])
for s in seen:
 p=pos({'progress':{'levels_completed':s[0]},'payload':{'frame':[s[1]]}})
 if p and p[0]>=7 and p[1]<=4:
  path=[];q=s
  while q!=root and q in parent:q,a=parent[q];path.append(a)
  path=path[::-1]
  g=s[1]; bs=[(x,y)for y,r in enumerate(g)for x,v in enumerate(r)if v in(4,7,10)]
  print(cps.get(s),p,'depth',len(path),'maxblue',max(x for x,y in bs),'path',path)
print('states',len(seen),'lastcp',cpnum)
