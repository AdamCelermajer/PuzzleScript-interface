"""Owned replacement campaigns and merged live status; no personal config edits."""
import json,time,sys,subprocess,threading,uuid,shutil,tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from avo.docker.batch import save,stop_owned
from avo.docker.launch import stage_controller,ROOT
from avo.monitor_evolution import evolution_snapshot

def main():
 base=Path(sys.argv[1]).resolve(); original=json.loads((base/'batch.json').read_text()); out=base/'repairs';out.mkdir(exist_ok=True)
 path=out/'repairs.json'
 manifest=json.loads(path.read_text()) if path.exists() else {'deadline_epoch':original['deadline_epoch'],'runs':[]}
 manifest['finished']=False
 queue=out/'queue.json'; source=out/'controller';source.mkdir(exist_ok=True)
 credentials=Path(tempfile.mkdtemp(prefix='avo-repair-oauth-'));shutil.copyfile(Path.home()/'.codex/auth.json',credentials/'auth.json');(credentials/'config.toml').write_text('# private repair login only\n')
 processes=[];logs=[];seen={p.name for p in out.iterdir() if p.is_dir() and p.name!='controller'}
 def snapshot():
  current=json.loads((base/'status.json').read_text());current['now']=time.time()
  for repair in manifest['runs']:
   row=current['runs'][repair['index']];progress=evolution_snapshot(Path(repair['output'])/'campaign')
   progress['hypotheses_evaluated']+=repair['previous_evaluated']
   row.update(status=repair['status'],progress=progress,attempt=repair['attempt'])
   try:
    lineage=json.loads((Path(repair['output'])/'campaign/lineage.json').read_text());values=[e['fitness'] for e in lineage['evaluations'] if isinstance(e.get('fitness'),(float,int))]
    if row.get('best_fitness') is not None:values.append(row['best_fitness'])
    row['best_fitness']=max(values) if values else None
   except (OSError,ValueError):pass
  current['finished']=manifest['finished'] and original['deadline_epoch']<=time.time()
  return current
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   body=json.dumps(snapshot()).encode();self.send_response(200);self.send_header('Access-Control-Allow-Origin','*');self.send_header('Cache-Control','no-store');self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
  def log_message(self,*args):pass
 server=ThreadingHTTPServer(('127.0.0.1',58180),Handler);manifest['status_url']=f'http://127.0.0.1:{server.server_port}/status';save(path,manifest)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 subprocess.Popen([sys.executable,'-m','avo.docker.batch','--watchdog',str(path)],cwd=ROOT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:
  while time.time()<manifest['deadline_epoch']:
   entries=json.loads(queue.read_text()) if queue.exists() else []
   for entry in entries:
    if entry['id'] in seen:continue
    index=entry['index'];prior=next((r for r in reversed(manifest['runs']) if r['index']==index),None)
    old=original['runs'][index] if prior is None else prior
    live=subprocess.run(['docker','inspect','--format','{{.State.Running}}',old['container']],capture_output=True,text=True)
    if live.returncode==0 and live.stdout.strip()=='true':continue
    remaining=int(manifest['deadline_epoch']-time.time()-35)
    if remaining<120:continue
    seen.add(entry['id']);target=out/entry['id'];target.mkdir();cmd=list(original['runs'][index]['command'])
    name='avo-isolated-'+uuid.uuid4().hex;cmd[cmd.index('--name')+1]=name
    for i,arg in enumerate(cmd):
     if arg.startswith('type=bind,'):
      if 'dst=/controller' in arg:cmd[i]=f'type=bind,src={source},dst=/controller,readonly'
      elif 'dst=/results' in arg:cmd[i]=f'type=bind,src={target},dst=/results'
      elif 'dst=/credentials' in arg:cmd[i]=f'type=bind,src={credentials},dst=/credentials,readonly'
    for flag in ['--max-wall-seconds','--player-max-wall-seconds']:cmd[cmd.index(flag)+1]=str(remaining)
    oldroot=Path(old.get('output',str(base/original['runs'][index]['run'])))/'campaign'
    lineage=json.loads((oldroot/'lineage.json').read_text()) if (oldroot/'lineage.json').exists() else {}
    spent=(prior.get('previous_registered',0) if prior else 0)+len(lineage.get('candidates',[]))
    evaluated=(prior.get('previous_evaluated',0) if prior else 0)+len(lineage.get('evaluations',[]))
    if spent>=20:continue
    if entry.get('resume') and oldroot.exists():
     shutil.copytree(oldroot,target/'campaign')
     cmd.append('--resume-saved-campaign')
     spent=prior.get('previous_registered',0) if prior else 0
     evaluated=0
    cmd[cmd.index('--max-evaluations')+1]=str(20-spent)
    log=(target/'console.txt').open('w');logs.append(log)
    repair={'index':index,'game':original['runs'][index]['game'],'container':name,'output':str(target),'attempt':2 if prior is None else prior['attempt']+1,'previous_registered':spent,'previous_evaluated':evaluated,'status':'starting','reason':entry['reason']}
    manifest['runs'].append(repair);save(path,manifest)
    proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=log);processes.append((repair,proc))
   for r,p in processes:r['status']='running' if p.poll() is None else ('completed' if p.returncode==0 else 'failed')
   try:
    save(path,manifest);save(out/'status.json',snapshot())
   except OSError as exc:
    print(f'Status save deferred: {type(exc).__name__}',flush=True)
   time.sleep(2)
 finally:
  stop_owned(manifest)
  for r,p in processes:
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:p.terminate()
   r['status']='stopped at deadline' if time.time()>=manifest['deadline_epoch'] else 'failed'
  manifest['finished']=True;save(path,manifest)
  for f in logs:f.close()
  (credentials/'auth.json').unlink(missing_ok=True);(credentials/'config.toml').unlink(missing_ok=True);credentials.rmdir()
 threading.Event().wait()
if __name__=='__main__':main()
