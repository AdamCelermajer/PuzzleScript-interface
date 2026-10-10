from pathlib import Path
from unittest.mock import patch
import json
from types import SimpleNamespace
import pytest
from avo.docker import launch
from avo.docker.launch import stage_controller, docker_command


def test_workspace_uses_disposable_disk_volume_not_memory(tmp_path):
    command = docker_command(tmp_path / 'source', tmp_path / 'output', [])
    assert 'type=volume,dst=/home/controller' in command
    assert not any('/home/controller:' in arg for arg in command)
    assert '--rm' in command
    assert command[command.index('--memory') + 1] == '2g'
    assert 'AVO_TRACE_DETAIL=compact' in command
    assert 'AVO_TRACE_DETAIL=full' in docker_command(tmp_path / 'source', tmp_path / 'output', [], 'full')


def test_explicit_resume_passes_flag_and_preserves_lineage(tmp_path):
    output = tmp_path / 'resume'
    campaign = output / 'campaign'
    campaign.mkdir(parents=True)
    (campaign / 'evolution_config.json').write_text(json.dumps({
        'profile_settings': {'game_id': 'ps_test-v1'}, 'world_model_mode': 'final-only'}))
    lineage = campaign / 'lineage.json'
    lineage.write_text('{"candidates": [], "evaluations": []}')
    (output / 'isolation_preflight.json').write_text('{"passed": true}')
    args = ['launch', '--campaign', '--resume-saved-campaign', '--output-dir', str(output),
            '--game-id', 'ps_test-v1', '--backend-url', 'http://test',
            '--optimizer-model', 'gpt-6-astra', '--player-model', 'gpt-5.6-luna',
            '--optimizer-service-tier', 'priority',
            '--max-evaluations', '10', '--research-moves', '500', '--solver-moves', '500']
    with patch('sys.argv', args), patch.object(launch, 'stage_controller'), \
         patch.object(launch, 'stage_credentials', return_value=[]), \
         patch.object(launch.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
        launch.main()
    assert '--resume-saved-campaign' in run.call_args_list[0].args[0]
    assert run.call_args_list[0].args[0][run.call_args_list[0].args[0].index('--optimizer-service-tier') + 1] == 'priority'
    assert json.loads(lineage.read_text()) == {'candidates': [], 'evaluations': []}
    args[args.index('--game-id') + 1] = 'ps_other-v1'
    with patch('sys.argv', args), pytest.raises(ValueError, match='Cannot change game'):
        launch.main()


def test_staging_excludes_game_sources_rules_credentials_and_histories(tmp_path):
    root=tmp_path/'repo'
    files=['avo/run.py','client/arc/types.py','studies/codex_agent/session.py',
           'avo/output/history.txt','client/rules/game/rules.py','avo/tests/test_secret.py',
           'puzzlescript_interface/games/game/script.txt','.env','auth.json']
    for name in files:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
    destination=tmp_path/'staged';destination.mkdir()
    with patch('avo.docker.launch.ROOT',root):stage_controller(destination)
    staged={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    assert staged=={'avo/run.py','client/arc/types.py','studies/codex_agent/session.py','AGENTS.md'}
