import json
from pathlib import Path
root=Path(__file__).parent
names={'c':'correct','p':'partial','w':'wrong','a':'absent'}
def save(seg,cp,beliefs,notebooks='aaaaaaaa',notes=None,both=()):
 p=root/f'seg-{seg}'/'labels.json'
 arr=json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
 labels={}
 for i,(b,n) in enumerate(zip(beliefs,notebooks),1):
  r=f'M{i}'; b=names[b];n=names[n]
  s='none' if b=='absent' else ('both' if i in both else 'notebook' if b==n else 'thinking')
  labels[r]={'belief':b,'source':s,'notebook':n}
  if notes and i in notes: labels[r]['note']=notes[i]
 assert not arr or arr[-1]['cp']<cp
 arr.append({'cp':cp,'labels':labels})
 p.write_text(json.dumps(arr,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
if __name__=='__main__':
 save(0,0,'cwaccaaa',notes={1:'T: The available actions are just the 5 movement/undo actions and RESET. There are no other actions.',2:'T: So pushing doesn\'t work (or the box is immovable).',3:'T: No change — can\'t move up from the top row. The boundary blocks. Good.',4:'T: When on bright, can only step on bright (or the goal); when on dark, can only step on dark',5:'T: the goal {4} is accessible from any class',6:'T: the orange box {3} blocks.',7:'T: the orange box {3} blocks.',8:'T: Now, the win condition: there are 4 levels. What does the level require?'})

