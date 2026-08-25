import json
h=json.load(open('h.json'))
for t in h['transitions'][-20:]:
 g=t['after']['payload']['frame'][-1]
 print(t['sequence'],t['action']['id'],[(r,c,v) for r,row in enumerate(g) for c,v in enumerate(row) if v in (9,11,12)])
