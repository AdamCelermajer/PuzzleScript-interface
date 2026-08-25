exec(open('mine.py').read().split("for s in seen:")[0])
target=next(s for s,c in cps.items() if c=='cp_273')
chain=[];q=target
while q!=root:
 b,a=parent[q];chain.append((a,q));q=b
chain=chain[::-1]
print('root',pos(Ts[0]['before']))
for a,s in chain:
 o={'progress':{'levels_completed':s[0]},'payload':{'frame':[s[1]]}}
 print(a,pos(o))
