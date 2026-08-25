import json
D=json.load(open('history.json'))
for t in D['transitions']:
 b=t['before']['payload']['frame'][-1]; a=t['after']['payload']['frame'][-1]
 dif=[]
 for y,(br,ar) in enumerate(zip(b,a)):
  for x,(u,v) in enumerate(zip(br,ar)):
   if u!=v:dif.append((x,y,u,v))
 print(t['sequence'],t['episode'],t['action']['id'],'status',t['after']['status'],'prog',t['after']['progress'],'diff',dif)
