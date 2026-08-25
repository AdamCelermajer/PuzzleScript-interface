import subprocess,json
s=subprocess.check_output(['python','avo_tool.py','history'],text=True);j=json.loads(s[s.find('{'):])
e=max(t['episode'] for t in j['transitions']);print('ep',e)
for t in j['transitions']:
 if t.get('episode')==e:
  g=t['after']['payload']['frame'][-1];o=[(v,r,c) for r,row in enumerate(g) for c,v in enumerate(row) if v not in(0,1,4,5,6)]
  print(t['sequence'],t['action']['id'],o)
