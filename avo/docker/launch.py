"""Trusted Windows launcher for Linux-isolated AVO; default is model-free preflight."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import tempfile
import os
from pathlib import Path
from uuid import uuid4

# Also support direct script invocation by existing launcher clients.
if __package__ in {None, ""}:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from avo.client.model_provider import API_PROVIDERS, api_key, resolve_model

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'avo-puzzlescript-isolated:local'

def stage_controller(destination: Path) -> None:
    # No games, .env, personal config, histories or model credentials in this tree.
    for package in ('avo', 'client', 'studies'):
        for source in (ROOT / package).rglob('*'):
            relative = source.relative_to(ROOT)
            if any(part in {'output', '__pycache__', '.venv', 'rules', 'tests'} for part in relative.parts):
                continue
            if source.is_file() and source.suffix in {'.py', '.md', '.txt', '.toml'}:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    (destination / 'AGENTS.md').write_text('Private controller canary. Not agent instructions.\n')

def docker_command(source: Path, output: Path, args: list[str], trace_detail: str | None = None) -> list[str]:
    return ['docker', 'run', '--name', 'avo-isolated-'+uuid4().hex, '--rm', '--init', '--read-only',
            '--cap-drop', 'ALL', '--cap-add', 'SYS_ADMIN', '--cap-add', 'SETUID', '--cap-add', 'SETGID', '--cap-add', 'SETFCAP',
            '--security-opt', 'no-new-privileges', '--security-opt', 'seccomp=unconfined',
            '--pids-limit', '256', '--memory', '2g', '--cpus', '2',
            '--tmpfs', '/tmp:rw,exec,nosuid,size=256m',
            '--mount', 'type=volume,dst=/home/controller',
            '--env', f'AVO_TRACE_DETAIL={trace_detail or os.environ.get("AVO_TRACE_DETAIL", "compact")}',
            '--mount', f'type=bind,src={source},dst=/controller,readonly',
            '--mount', f'type=bind,src={output},dst=/results',
            IMAGE, *args]


def stage_credentials(credentials: Path, models: list[str]) -> list[str]:
    providers = {resolve_model(model)[0] for model in models}
    options = ['--mount', f'type=bind,src={credentials},dst=/credentials,readonly',
               '--env', 'CODEX_HOME=/credentials']
    if 'openai' in providers:
        auth = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))) / 'auth.json'
        payload = json.loads(auth.read_text(encoding='utf-8'))
        if not payload.get('tokens'):
            raise RuntimeError('Existing ChatGPT OAuth login is required for OpenAI models')
        shutil.copyfile(auth, credentials/'auth.json')
    for provider in sorted(providers & API_PROVIDERS.keys()):
        key = api_key(provider, env_file=ROOT/'.env')
        target = credentials/f'{provider}.key'
        target.write_text(key, encoding='utf-8')
        target.chmod(0o600)
        options += ['--env', f'AVO_{provider.upper()}_KEY_FILE=/credentials/{provider}.key']
    (credentials/'config.toml').write_text('# synthetic config canary\n')
    return options

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--campaign', action='store_true')
    parser.add_argument('--resume-saved-campaign', action='store_true',
                        help='Continue an explicitly staged campaign in the output directory')
    parser.add_argument('--game-id')
    parser.add_argument('--backend-url')
    parser.add_argument('--optimizer-model')
    parser.add_argument('--player-model')
    parser.add_argument('--effort', default='high')
    parser.add_argument('--optimizer-effort')
    parser.add_argument('--player-effort')
    parser.add_argument('--trace-detail', choices=['compact', 'full'], default=None)
    parser.add_argument('--harness', choices=['codex', 'tools', 'raw'], default='codex')
    parser.add_argument('--provider', default='', help='Pin one OpenRouter provider slug for all agents')
    parser.add_argument('--optimizer-service-tier', default='', choices=['', 'priority'])
    parser.add_argument('--player-service-tier', default='', choices=['', 'priority'])
    parser.add_argument('--max-wall-seconds', type=int, default=14400)
    parser.add_argument('--player-max-wall-seconds', type=int, default=None,
                        help='Per-candidate research time; defaults to the campaign wall limit')
    parser.add_argument('--world-model-mode', choices=['final-only', 'between-hypotheses'], default='final-only')
    parser.add_argument('--max-evaluations', type=int)
    parser.add_argument('--research-moves', type=int)
    parser.add_argument('--solver-moves', type=int)
    options = parser.parse_args()
    if options.resume_saved_campaign and not options.campaign:
        parser.error('--resume-saved-campaign requires --campaign')
    if options.campaign:
        required=('game_id','backend_url','optimizer_model','player_model','max_evaluations','research_moves','solver_moves')
        if any(getattr(options,key) is None for key in required):
            parser.error('Campaign requires game, backend, both models and explicit evaluation/research/solver budgets')
        if any(getattr(options,key)<=0 for key in ('max_evaluations','research_moves','solver_moves')):
            parser.error('Budgets must be positive')
        for model in (options.optimizer_model, options.player_model):
            if options.provider and resolve_model(model)[0] == 'nanogpt':
                parser.error('Provider pinning is only supported for OpenRouter')
            if resolve_model(model)[0] not in API_PROVIDERS and options.harness != 'codex':
                parser.error('The tools and raw harnesses require OpenRouter or NanoGPT model IDs')
        if resolve_model(options.player_model)[0] in API_PROVIDERS and options.player_service_tier:
            parser.error('API-key models do not support the Codex service tier setting')
    output = Path(options.output_dir).resolve()
    if options.resume_saved_campaign:
        saved = json.loads((output / 'campaign' / 'evolution_config.json').read_text(encoding='utf-8'))
        json.loads((output / 'campaign' / 'lineage.json').read_text(encoding='utf-8'))
        if saved.get('profile_settings', {}).get('game_id') != options.game_id:
            raise ValueError('Cannot change game while continuing a campaign')
        if saved.get('world_model_mode', 'off') != options.world_model_mode:
            raise ValueError('Cannot change world-model condition while continuing a campaign')
        if saved.get('harness', 'codex') != options.harness or saved.get('provider', '') != options.provider:
            raise ValueError('Cannot change the agent harness while continuing a campaign')
    elif options.campaign and output.exists():
        raise ValueError('Campaign requires a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='avo-controller-') as folder, tempfile.TemporaryDirectory(prefix='avo-credentials-') as credentials_folder:
        source = Path(folder)
        stage_controller(source)
        arguments=['-m', 'avo.docker.preflight']
        if options.campaign:
            arguments=['-m','avo.docker.campaign', '--profile','puzzlescript',
                '--set',f'game_id={options.game_id}', '--set',f'backend_url={options.backend_url}',
                '--output-dir','/results/campaign', '--optimizer-model',options.optimizer_model,
                '--player-model',options.player_model,'--optimizer-effort',options.optimizer_effort or options.effort,
                '--player-effort',options.player_effort or options.effort,
                '--optimizer-service-tier',options.optimizer_service_tier,
                '--player-service-tier',options.player_service_tier,
                '--world-model-mode',options.world_model_mode,
                '--harness',options.harness, '--provider',options.provider,
                '--max-wall-seconds',str(options.max_wall_seconds),
                '--player-max-wall-seconds',str(options.player_max_wall_seconds if options.player_max_wall_seconds is not None else options.max_wall_seconds),
                '--max-evaluations',str(options.max_evaluations),
                '--player-max-environment-steps',str(options.research_moves),
                '--fresh-solver-max-environment-steps',str(options.solver_moves),
                '--solver-self-check-max-environment-steps',str(options.solver_moves)]
            if options.resume_saved_campaign:
                arguments.append('--resume-saved-campaign')
        command = docker_command(source, output, arguments, options.trace_detail)
        (output / 'launcher.json').write_text(json.dumps({'container': command[command.index('--name')+1]}), encoding='utf-8')
        if options.campaign:
            command[command.index(IMAGE):command.index(IMAGE)] = stage_credentials(
                Path(credentials_folder), [options.optimizer_model, options.player_model])
        try:
            result = subprocess.run(command, cwd=ROOT)
        finally:
            # Exact launcher-owned name, never a sweep over unrelated containers.
            subprocess.run(['docker','rm','-f','-v',command[command.index('--name')+1]],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        if result.returncode:
            raise SystemExit(result.returncode)
        if not options.campaign:
            report = json.loads((output / 'isolation_preflight.json').read_text())
            if not report.get('passed'):
                raise SystemExit('Container sandbox preflight did not pass')

if __name__ == '__main__':
    main()
