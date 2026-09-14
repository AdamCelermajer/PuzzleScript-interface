"""Six bounded campaigns, local live monitor, and independent deadline watchdog."""
import argparse, concurrent.futures, json, os, shutil, subprocess, sys, tempfile, time
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from avo.docker.launch import ROOT, IMAGE, stage_controller, docker_command
from avo.monitor_evolution import evolution_snapshot

GAMES=[('Modality','ps_modality-v1','Easy'),('Purple','ps_purple-v1','Easy'),('Knightoban','ps_knightoban-v1','Medium'),('Magnetic','ps_magnetic-v1','Medium'),('Atlas Shrank','ps_atlas_shrank-v1','Hard'),('Enqueue','ps_enqueue-v1','Hard')]

def save(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2),encoding='utf8')
    for attempt in range(30):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt==29:raise
            time.sleep(.1)

def stop_owned(manifest):
    for run in manifest.get('runs',[]):
        name=run.get('container','')
        if name.startswith('avo-isolated-'):
            subprocess.run(['docker','kill',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)

def watchdog(path):
    while True:
        data=json.loads(path.read_text())
        if data.get('finished'):return
        remaining=data['deadline_epoch']-time.time()
        if remaining<=0:
            stop_owned(data)
            (path.parent/'deadline-stop.txt').write_text(datetime.now().astimezone().isoformat())
            return
        time.sleep(min(5,remaining))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir');p.add_argument('--deadline');p.add_argument('--backend-url');p.add_argument('--watchdog');a=p.parse_args()
    if a.watchdog:return watchdog(Path(a.watchdog))
    out=Path(a.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    deadline=datetime.fromisoformat(a.deadline).timestamp()
    if deadline-time.time()<120:raise RuntimeError('Deadline too close')
    manifest={'started_at':datetime.now().astimezone().isoformat(),'deadline':a.deadline,'deadline_epoch':deadline,'finished':False,'runs':[]}
    path=out/'batch.json'
    source=out/'controller';source.mkdir();stage_controller(source)
    credentials=Path(tempfile.mkdtemp(prefix='avo-batch-oauth-'))
    auth=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'auth.json'
    if not json.loads(auth.read_text()).get('tokens'):raise RuntimeError('OAuth login missing')
    shutil.copyfile(auth,credentials/'auth.json');(credentials/'config.toml').write_text('# synthetic private config\n')
    logs=[];processes=[]
    def snapshot():
        data=dict(manifest);data['now']=time.time();data['runs']=[]
        for r in manifest['runs']:
            item=dict(r)
            try:item['progress']=evolution_snapshot(out/r['run']/'campaign')
            except Exception:item['progress']={}
            try:
                lineage=json.loads((out/r['run']/'campaign/lineage.json').read_text())
                values=[e['fitness'] for e in lineage.get('evaluations',[]) if isinstance(e.get('fitness'),(int,float))]
                item['best_fitness']=max(values) if values else None
            except (OSError,ValueError):item['best_fitness']=None
            data['runs'].append(item)
        return data
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/status'):
                body=json.dumps(snapshot()).encode();mime='application/json'
            else:body=(ROOT/'avo/docker/monitor.html').read_bytes();mime='text/html; charset=utf-8'
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    manifest['monitor_url']=f'http://127.0.0.1:{http.server_port}'
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
        for i,(title,game,difficulty) in enumerate(GAMES):
            target=out/f'run-{i+1:04d}';target.mkdir()
            arguments=['-m','avo.docker.campaign','--profile','puzzlescript','--set',f'game_id={game}',
                '--set',f'backend_url={a.backend_url}','--output-dir','/results/campaign',
                '--optimizer-model','gpt-6-astra','--optimizer-effort','low',
                '--player-model','gpt-5.6-luna','--player-effort','high','--player-service-tier','priority',
                '--max-evaluations','20','--player-max-environment-steps','300',
                '--fresh-solver-max-environment-steps','1500','--solver-self-check-max-environment-steps','1500',
                '--max-wall-seconds',str(max(1,int(deadline-time.time()-35))),
                '--player-max-wall-seconds',str(max(1,int(deadline-time.time()-40)))]
            cmd=docker_command(source,target,arguments)
            cmd[cmd.index(IMAGE):cmd.index(IMAGE)]=['--mount',f'type=bind,src={credentials},dst=/credentials,readonly','--env','CODEX_HOME=/credentials']
            manifest['runs'].append({'run':target.name,'game':title,'difficulty':difficulty,'container':cmd[cmd.index('--name')+1],'status':'prepared','command':cmd})
        save(path,manifest)
        subprocess.Popen([sys.executable,'-m','avo.docker.batch','--watchdog',str(path)],cwd=ROOT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for i,r in enumerate(manifest['runs']):
            log=(out/r['run']/'console.txt').open('w',encoding='utf8');logs.append(log)
            proc=subprocess.Popen(r['command'],cwd=ROOT,stdout=log,stderr=log);processes.append(proc);r['status']='starting';save(path,manifest)
            if i==0:
                # First authenticated request must get past the guard before fan-out.
                limit=time.time()+180
                while time.time()<limit and proc.poll() is None:
                    root=out/r['run']/'campaign/optimizer_analysis'
                    allowed=False
                    for request in root.rglob('request-*.json'):
                        try:
                            captured=json.loads(request.read_text())
                            allowed |= captured.get('forwarding_allowed') is True and bool(captured.get('request',{}).get('input'))
                        except (OSError,ValueError):pass
                    if allowed:break
                    time.sleep(2)
                if proc.poll() is not None:
                    raise RuntimeError('First campaign failed; inspect run-0001/console.txt')
                if not allowed:raise RuntimeError('No validated model request; six-way launch cancelled')
        while time.time()<deadline and any(p.poll() is None for p in processes):
            for r,proc in zip(manifest['runs'],processes):
                r['status']='running' if proc.poll() is None else ('completed' if proc.returncode==0 else 'failed')
            save(path,manifest);save(out/'status.json',snapshot())
            # Persist unfinished notes before the hard stop destroys tmpfs state.
            if deadline-time.time()<45 and not manifest.get('workspaces_saved'):
                for r in manifest['runs']:
                    subprocess.run(['docker','exec',r['container'],'sh','-c','tar -czf /results/unfinished-workspaces.tar.gz -C /home/controller/.avo/isolated $(find /home/controller/.avo/isolated -maxdepth 1 -type d -name "w-*" -printf "%f ")'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                manifest['workspaces_saved']=True
            time.sleep(2)
    except Exception as exc:
        manifest['error']=f'{type(exc).__name__}: {exc}'
    finally:
        stop_owned(manifest)
        for proc in processes:
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.terminate()
        for log in logs:log.close()
        for r,proc in zip(manifest['runs'],processes):
            r['status']='stopped at deadline' if time.time()>=deadline else ('completed' if proc.returncode==0 else 'failed')
        manifest['finished']=True;save(path,manifest);save(out/'status.json',snapshot())
        (credentials/'auth.json').unlink(missing_ok=True);(credentials/'config.toml').unlink(missing_ok=True);credentials.rmdir()
    # Keep the read-only monitor available after completion.
    http.serve_forever()

if __name__=='__main__':main()
