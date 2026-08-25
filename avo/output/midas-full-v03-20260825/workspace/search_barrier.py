import subprocess,json,random
random.seed(19)
def call(args):
 p=subprocess.run(['python','avo_tool.py']+args,text=True,capture_output=True)
 s=p.stdout+p.stderr;i=s.find('{')
 try:return json.loads(s[i:]) if i>=0 else {'raw':s}
 except:return {'raw':s}
def coord(j):
 try:
  g=j['transition']['after']['payload']['frame'][-1]
  for r,row in enumerate(g):
   for c,v in enumerate(row):
    if v in(2,8): return r,c
 except:return None
for t in range(8):
 call(['reset','--reason','Bounded search for a transition across the central barrier.'])
 seq=[]
 for k in range(20):
  choices=['ACTION1']*4+['ACTION4']*5+['ACTION3']*3+['ACTION2','ACTION5','ACTION7']
  a=random.choice(choices)
  if len(seq)>1 and seq[-1]==seq[-2]==a:a=random.choice(['ACTION1','ACTION3','ACTION4','ACTION5'])
  j=call(['probe',a,'--rationale','Bounded exploration for a barrier-crossing movement sequence.'])
  if 'raw' in j and 'acknowledgement' in j['raw']:
   call(['acknowledge_supervisor','Switch action family and reset after the bounded trial.']);continue
  seq.append(a); p=coord(j)
  if p and p[1]>=9:
   print('CROSSED',t,k,p,' '.join(x[-1] for x in seq),flush=True);raise SystemExit
 print('trial',t,'maxdone',' '.join(x[-1] for x in seq),flush=True)
print('NONE')
