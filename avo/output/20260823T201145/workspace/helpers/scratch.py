GRID=[
 [1,1,1,1,0,0],
 [1,0,5,1,0,0],
 [1,3,0,1,1,1],
 [1,2,0,0,0,1],
 [1,0,0,3,0,1],
 [1,0,0,1,1,1],
 [1,1,1,1,0,0],
]
R=len(GRID);C=len(GRID[0])
walls={(r,c) for r in range(R) for c in range(C) if GRID[r][c]==1}
boxes={(r,c) for r in range(R) for c in range(C) if GRID[r][c] in (3,4)}
p=(3,1)
D={'U':(-1,0),'D':(1,0),'L':(0,-1),'R':(0,1)}
NAME={'U':'ACTION1','D':'ACTION2','L':'ACTION3','R':'ACTION4'}
path="RRRDLULLDDRULURUULDRDDRRULDLUU"
for i,a in enumerate(path):
    dr,dc=D[a]
    n=(p[0]+dr,p[1]+dc)
    if n in walls: print(i,a,"BLOCKED wall");continue
    if n in boxes:
        nn=(n[0]+dr,n[1]+dc)
        if nn in walls or nn in boxes: print(i,a,"BLOCKED box");continue
        boxes.discard(n);boxes.add(nn)
    p=n
    print(i,a,"player",p,"boxes",sorted(boxes))
print("boxes final",sorted(boxes))
print(" ".join(NAME[a] for a in path))
