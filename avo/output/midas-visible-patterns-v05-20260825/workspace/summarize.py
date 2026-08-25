import json
h=json.load(open('history.json'))
for t in h['transitions']:
 b=t['before']['payload']['frame'][-1]; a=t['after']['payload']['frame'][-1]
 print(t['sequence'],t['action']['id'],'progress',t['after'].get('progress'))
 print('\n'.join(''.join(str(x) for x in row) for row in a)); print()
