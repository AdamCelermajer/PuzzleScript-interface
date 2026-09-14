"""Runs inside the trusted controller container; no model/authentication needed."""
import json
import socket
from pathlib import Path
from avo.isolation import IsolatedRuntime, new_workspace

output = Path('/results')
runtime = IsolatedRuntime(new_workspace(), output, '/usr/local/bin/codex')
try:
    # Make the config canary real: absence alone is not evidence of denied reads.
    runtime.personal_codex.mkdir(parents=True, exist_ok=True)
    if not (runtime.personal_codex / 'config.toml').exists():
        (runtime.personal_codex / 'config.toml').write_text('# synthetic private config\n')
    result = runtime.preflight()
    # Exercise the same app-server command path used by agent tools as well.
    from openai_codex.client import CodexClient, CodexConfig
    from pydantic import BaseModel
    class ExecResult(BaseModel):
        exitCode: int
        stdout: str
        stderr: str
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    code = (
        'import json,pathlib,socket; '
        'paths=["/controller/AGENTS.md","/results",'+repr(str(runtime.personal_codex/'config.toml'))+']; '
        'readable=[pathlib.Path(p).exists() for p in paths]; '
        '\nnetwork=False\ntry:\n s=socket.socket(); s.settimeout(1)\n'
        f' network=s.connect_ex(("127.0.0.1",{listener.getsockname()[1]}))==0\n'
        'except OSError: pass\n'
        'pathlib.Path("app-server-write.txt").write_text("ok"); '
        'caps=next(x.split()[1] for x in pathlib.Path("/proc/self/status").read_text().splitlines() if x.startswith("CapEff:")); '
        'print(json.dumps({"readable":readable,"network":network,"effective_caps":caps})); '
        'assert not any(readable) and not network and int(caps,16)==0'
    )
    try:
        with CodexClient(CodexConfig(codex_bin=runtime.codex_bin,cwd=str(runtime.workspace),env=runtime.env)) as client:
            client.initialize()
            check = client.request('command/exec', {'command':[str(runtime.python),'-c',code],
                'cwd':str(runtime.workspace),'timeoutMs':15000}, response_model=ExecResult).model_dump()
        if check['exitCode'] != 0:
            raise RuntimeError('App-server isolation check failed: '+str(check))
        result['app_server'] = json.loads(check['stdout'])
    finally:
        listener.close()
    result['backend'] = 'docker-linux-bwrap'
    result['host_personal_config_mounted'] = False
    (output / 'isolation_preflight.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
finally:
    runtime.close()
