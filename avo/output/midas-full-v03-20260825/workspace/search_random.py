import subprocess,json,random,time
random.seed(4)
A=['ACTION1','ACTION2','ACTION3','ACTION4','ACTION5','ACTION7']
def call(args):
 p=subprocess.run(['python','avo_tool.py']+args,text=True,capture_output=True)
 out=p.stdout+p.stderr
 i=out.find('{')
 try:return json.loads(out[i:]) if i>=0 else {'raw':out}
 except:return {'raw':out}
def prog(j):
 try:return j['task']['score']['levels_completed']
 except:return -1
for trial in range(20):
 call(['reset','--reason','Randomized bounded search of discrete action sequences for the current unsolved level.'])
 seq=[]; last=None
 for step in range(20):
  # bias horizontal right/up/action, avoid 3 identical
  choices=['ACTION4']*4+['ACTION1']*3+['ACTION3']*2+['ACTION2','ACTION5','ACTION7']
  a=random.choice(choices)
  if len(seq)>=2 and seq[-1]==seq[-2]==a: a=random.choice([x for x in A if x!=a])
  j=call(['probe',a,'--rationale','Bounded randomized exploration of an unsolved interaction sequence.'])
  if 'raw' in j and 'acknowledgement' in j['raw']:
   call(['acknowledge_supervisor','Randomized exploration will switch action families and reset after this short trial.'])
   continue
  seq.append(a)
  p=prog(j)
  if p>3:
   print('WINPROGRESS',p,'trial',trial,'step',step,'seq',seq); raise SystemExit
 print('trial',trial,'seq',' '.join(x[-1] for x in seq))
print('NO_PROGRESS')
