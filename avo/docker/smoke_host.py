"""Launch six model-free isolated solver checks against an owned local stack."""
import concurrent.futures
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import uvicorn
from puzzlescript_interface.api.app import create_app
from puzzlescript_interface.api.client import PuzzleScriptClient
from avo.docker.launch import ROOT, stage_controller, docker_command

games=['ps_modality-v1','ps_purple-v1','ps_knightoban-v1','ps_magnetic-v1','ps_atlas_shrank-v1','ps_enqueue-v1']
output=ROOT/'output/avo-docker-six-smoke'
output.mkdir(parents=True,exist_ok=True)
node=subprocess.Popen(['node','-e',"const {app}=require('./puzzlescript_interface/runtime/server');const s=app.listen(0,'127.0.0.1',()=>console.log('PORT='+s.address().port));"],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
server=None
try:
    while True:
        line=node.stdout.readline()
        if line.startswith('PORT='):
            port=int(line.split('=')[1]);break
        if not line:raise RuntimeError('Node runtime exited')
    # Runtime action logging must be drained during concurrent HTTP requests.
    def drain():
        with (output/'node.log').open('w',encoding='utf8') as log:
            for line in node.stdout:log.write(line)
    threading.Thread(target=drain,daemon=True).start()
    app=create_app(puzzlescript_client=PuzzleScriptClient(f'http://127.0.0.1:{port}'))
    sock=socket.socket();sock.bind(('0.0.0.0',0))
    api_port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    if not server.started:raise RuntimeError('ARC service failed to start')
    with tempfile.TemporaryDirectory(prefix='avo-controller-') as folder:
        source=Path(folder);stage_controller(source)
        def run(game):
            target=output/game;target.mkdir(exist_ok=True)
            cmd=docker_command(source,target,['-m','avo.docker.smoke','--backend-url',f'http://host.docker.internal:{api_port}','--game-id',game])
            try:
                result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
            finally:
                subprocess.run(['docker','rm','-f',cmd[cmd.index('--name')+1]],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            (target/'console.txt').write_text(result.stdout+result.stderr)
            return {'game':game,'passed':result.returncode==0,'return_code':result.returncode}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(run,games))
    (output/'summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
    if not all(r['passed'] for r in results):raise SystemExit(1)
finally:
    if server is not None:server.should_exit=True
    node.terminate();node.wait(timeout=10)
