import json
h=json.load(open('h.json'))
for t in h['transitions']:
 if t['sequence'] in (567,568,569,570,571,572,573,574,575):
  g=t['after']['payload']['frame'][-1]
  print(t['sequence'],t['action']['id'],[(r,c,v) for r,row in enumerate(g) for c,v in enumerate(row) if v not in (0,1,4,5,10)])
