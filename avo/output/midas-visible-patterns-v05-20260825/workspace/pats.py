import json
j=json.load(open('obs.json'))['observation']['metadata']['projection']['patterns']
for k in sorted(j,key=int):
 print(k); print('\n'.join(''.join(map(str,r)) for r in j[k]))
