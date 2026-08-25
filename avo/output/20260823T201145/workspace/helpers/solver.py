import sys, json
from collections import deque

INIT = [
 [1,1,1,1,0,0],
 [1,0,5,1,0,0],
 [1,0,0,1,1,1],
 [1,4,2,0,0,1],
 [1,0,0,3,0,1],
 [1,0,0,1,1,1],
 [1,1,1,1,0,0],
]
R=len(INIT); C=len(INIT[0])
DIRS={'U':(-1,0),'D':(1,0),'L':(0,-1),'R':(0,1)}
NAME={'U':'ACTION1','D':'ACTION2','L':'ACTION3','R':'ACTION4'}

def parse(grid):
    walls=set(); boxes=set(); goals=set(); player=None
    for r in range(R):
        for c in range(C):
            v=grid[r][c]
            if v==1: walls.add((r,c))
            elif v==2: player=(r,c)
            elif v==3: boxes.add((r,c))
            elif v==4: boxes.add((r,c))
            elif v==5: goals.add((r,c))
    return walls,boxes,goals,player

def solve(walls,boxes,goals,player,need_all=True):
    start=(player,frozenset(boxes))
    seen={start:None}
    q=deque([start])
    while q:
        st=q.popleft()
        p,bs=st
        if need_all:
            done = bs<=goals or all(b in goals for b in bs)
        else:
            done = any(b in goals for b in bs)
        if done and bs:
            path=[]
            cur=st
            while seen[cur]:
                prev,a=seen[cur]
                path.append(a); cur=prev
            return path[::-1]
        for d,(dr,dc) in DIRS.items():
            np=(p[0]+dr,p[1]+dc)
            if np in walls: continue
            nb=bs
            if np in bs:
                nn=(np[0]+dr,np[1]+dc)
                if nn in walls or nn in bs: continue
                nb=frozenset((bs-{np})|{nn})
            ns=(np,nb)
            if ns not in seen:
                seen[ns]=(st,d)
                q.append(ns)
    return None

def show(path):
    if path is None: return "NO SOLUTION"
    return " ".join(NAME[a] for a in path)+f"   ({len(path)} moves)  raw={''.join(path)}"

if __name__=='__main__':
    walls,boxes,goals,player=parse(INIT)
    print("walls",sorted(walls))
    print("boxes",sorted(boxes),"goals",sorted(goals),"player",player)
    # variant A: both 3 and 4 are boxes, goal only 5, need any box on goal
    print("A any-box-on-5:", show(solve(walls,boxes,goals,player,need_all=False)))
    # variant B: only 3 is a box, 4 is a wall, goal 5
    w2=set(walls); w2.add((3,1))
    print("B box3 only, 4=wall, goal 5:", show(solve(w2,{(4,3)},goals,player,need_all=False)))
    # variant C: 3 is box, 4 is goal, 5 is goal
    print("C box3, goals {4,5}:", show(solve(walls,{(4,3)},{(3,1),(1,2)},player,need_all=False)))
    # variant D: 3 box, 4 goal only
    print("D box3, goal (3,1):", show(solve(walls,{(4,3)},{(3,1)},player,need_all=False)))
    # variant E: 3 and 4 boxes, goals {5} plus (3,1) already-on-goal => need both on goals
    print("E boxes{3,4}, goals{(1,2),(3,1)} all:", show(solve(walls,boxes,{(1,2),(3,1)},player,need_all=True)))
