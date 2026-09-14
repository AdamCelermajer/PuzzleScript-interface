"""Own only this batch's Node/API processes and stop them at the deadline."""
import argparse,json,socket,subprocess,threading,time
from datetime import datetime
from pathlib import Path
import uvicorn
from avo.docker.launch import ROOT
from puzzlescript_interface.api.app import create_app
from puzzlescript_interface.api.client import PuzzleScriptClient
p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);p.add_argument('--deadline',required=True);a=p.parse_args()
out=Path(a.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
node=subprocess.Popen(['node','-e',"const {app}=require('./puzzlescript_interface/runtime/server');const s=app.listen(0,'127.0.0.1',()=>console.log('PORT='+s.address().port));"],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
server=None
try:
    while True:
        line=node.stdout.readline()
        if line.startswith('PORT='):port=int(line.split('=')[1]);break
        if not line:raise RuntimeError('Node exited')
    def drain():
        with (out/'node.log').open('w',encoding='utf8') as log:
            for line in node.stdout:log.write(line);log.flush()
    threading.Thread(target=drain,daemon=True).start()
    sock=socket.socket();sock.bind(('0.0.0.0',0));api_port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(puzzlescript_client=PuzzleScriptClient(f'http://127.0.0.1:{port}')),log_level='error'))
    threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True).start()
    while not server.started:time.sleep(.05)
    (out/'stack.json').write_text(json.dumps({'backend_url':f'http://host.docker.internal:{api_port}','node_pid':node.pid}))
    while time.time()<datetime.fromisoformat(a.deadline).timestamp():time.sleep(1)
finally:
    if server:server.should_exit=True
    node.terminate();node.wait(timeout=10)
