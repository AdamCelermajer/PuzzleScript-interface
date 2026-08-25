import json
j=json.load(open('obs.json')); o=j['observation'];print(o['progress']);
for g in o['payload']['frame']:
 print('---');print('\n'.join(' '.join(map(str,r)) for r in g))
