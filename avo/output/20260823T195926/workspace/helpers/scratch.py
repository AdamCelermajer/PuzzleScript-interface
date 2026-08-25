import json
from collections import deque
s=json.load(open('current_state.json'))
g=[r[:] for r in s['grid']]
R,C=len(g),len(g[0])
def find(t):
    for r in range(R):
        for c in range(C):
            if g[r][c]==t: return (r,c)
print('player',find(2),'box',find(3),'four',find(4),'five',find(5))
# reachability of floor from player ignoring box
start=find(2)
seen={start};q=deque([start])
while q:
    r,c=q.popleft()
    for dr,dc in((-1,0),(1,0),(0,-1),(0,1)):
        n=(r+dr,c+dc)
        if 0<=n[0]<R and 0<=n[1]<C and g[n[0]][n[1]]!=1 and n not in seen:
            seen.add(n);q.append(n)
print('reachable',sorted(seen))
