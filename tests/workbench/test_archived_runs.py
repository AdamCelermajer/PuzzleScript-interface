"""Retired experiments remain readable but cannot launch retired backends."""
import json
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.catalog import snapshot
from workbench.experiments import ExperimentRequest, create_router, write_json
from workbench.experiment_job import run_job, stop_child
from workbench.submissions import submission


def test_archived_provider_and_harness_identity_are_preserved(tmp_path):
    run = 'output/archived/campaign'
    path = tmp_path/run; path.mkdir(parents=True)
    config = {'agent_backend':'opencode', 'player':{'model':'opencode/muse-spark-1.3-contributor-free'},
              'optimizer_model':'openrouter/test/model:free', 'profile_settings':{'game_id':'ps_modality-v1'}}
    (path/'evolution_config.json').write_text(json.dumps(config))
    for record in (snapshot(tmp_path, {})['runs'][0], submission(run, tmp_path)):
        assert record['agent_backend'] == record['model_provider'] == 'opencode'
        assert record['model'] == config['player']['model']
        assert record['optimizer_provider'] == 'openrouter'


def test_removed_backend_and_catalog_are_rejected_before_launch(tmp_path):
    app = FastAPI(); app.include_router(create_router(tmp_path))
    with TestClient(app) as client, patch('workbench.experiments.subprocess.Popen') as start:
        for endpoint in ('/experiments/preview', '/experiments'):
            response = client.post('/api/workbench'+endpoint, json={
                'kind':'avo','game_ids':['a'],'agent_backend':'opencode'})
            assert response.status_code == 422
        assert client.get('/api/workbench/model-catalog?provider=opencode').status_code == 422
        start.assert_not_called()
    with pytest.raises(ValueError):
        ExperimentRequest(kind='avo', game_ids=['a'], models=['opencode/muse'])


def test_saved_retired_job_cannot_restart_its_old_command(tmp_path):
    job = tmp_path/'job'; job.mkdir()
    write_json(job/'job.json', {'config':{'parallel':1,'max_hours':.1,'agent_backend':'opencode'},
        'runs':[{'status':'queued','kind':'avo','command':['old-opencode-launcher'],'output':str(job/'run')} ]})
    with patch('workbench.experiment_job.subprocess.Popen') as start:
        run_job(job)
        start.assert_not_called()
    saved = json.loads((job/'job.json').read_text())
    assert saved['status'] == 'failed' and 'retired' in saved['error']


def test_stop_removes_only_owned_codex_container(tmp_path):
    (tmp_path/'launcher.json').write_text('{"container":"avo-isolated-owned"}')
    process = Mock(); process.poll.return_value = None
    with patch('workbench.experiment_job.subprocess.run') as run:
        stop_child(process, {'kind':'avo','output':str(tmp_path)})
    assert run.call_args.args[0] == ['docker','rm','-f','avo-isolated-owned']
