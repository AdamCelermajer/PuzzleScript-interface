import json
import os
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.client.model_provider import resolve_model
from avo.docker.launch import stage_credentials
from avo.isolation import IsolatedRuntime, IsolationError


def test_provider_selection_is_explicit_and_keeps_native_id():
    assert resolve_model('gpt-5.6-sol') == ('openai', 'gpt-5.6-sol')
    assert resolve_model('openrouter/deepseek/deepseek-v4.1-flash') == ('openrouter', 'deepseek/deepseek-v4.1-flash')
    for model in ('openrouter/', 'openrouter/deepseek', 'openrouter/deepseek/', 'opencode/muse'):
        with pytest.raises(ValueError):
            resolve_model(model)
    with pytest.raises(ValueError, match='service tier'):
        CodexOAuthAgent(CodexOAuthConfig(model='openrouter/vendor/model', service_tier='priority'))


def test_key_is_controller_only_and_removed_on_close(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-secret')
    monkeypatch.delenv('AVO_OPENROUTER_KEY_FILE', raising=False)
    runtime = IsolatedRuntime(tmp_path/'workspace', tmp_path/'artifacts', 'codex')
    try:
        before = (runtime.private/'config.toml').read_text()
        runtime.authenticate_openrouter()
        assert runtime.env['OPENROUTER_API_KEY'] == 'unit-test-secret'
        assert (runtime.private/'config.toml').read_text() == before
        config = tomllib.loads(before)
        assert config['shell_environment_policy']['inherit'] == 'none'
        assert not config['shell_environment_policy']['set'].get('OPENROUTER_API_KEY')
        assert 'unit-test-secret' not in before
        assert not (runtime.private/'auth.json').exists()
    finally:
        runtime.close()
    assert 'OPENROUTER_API_KEY' not in runtime.env


def test_credential_staging_uses_only_needed_provider_and_project_key(tmp_path, monkeypatch):
    root = tmp_path/'project'; root.mkdir()
    (root/'.env').write_text('OPENROUTER_API_KEY=project-test-key\n')
    credentials = tmp_path/'credentials'; credentials.mkdir()
    monkeypatch.setenv('OPENROUTER_API_KEY', 'different-user-key')
    monkeypatch.setenv('CODEX_HOME', str(tmp_path/'missing-oauth-home'))
    monkeypatch.delenv('AVO_OPENROUTER_KEY_FILE', raising=False)
    with patch('avo.docker.launch.ROOT', root):
        options = stage_credentials(credentials, ['openrouter/vendor/model']*2)
    assert (credentials/'openrouter.key').read_text() == 'project-test-key'
    assert not (credentials/'auth.json').exists()
    assert 'project-test-key' not in str(options)
    assert 'AVO_OPENROUTER_KEY_FILE=/credentials/openrouter.key' in options
    assert os.environ['OPENROUTER_API_KEY'] == 'different-user-key'


def test_mixed_providers_stage_both_and_oauth_only_needs_no_router_key(tmp_path, monkeypatch):
    personal = tmp_path/'personal'; personal.mkdir()
    (personal/'auth.json').write_text(json.dumps({'tokens': {'test': 'synthetic'}}))
    keyfile = tmp_path/'key'; keyfile.write_text('file-test-key')
    monkeypatch.setenv('CODEX_HOME', str(personal))
    monkeypatch.setenv('AVO_OPENROUTER_KEY_FILE', str(keyfile))
    credentials = tmp_path/'mixed'; credentials.mkdir()
    stage_credentials(credentials, ['gpt-test', 'openrouter/vendor/model'])
    assert (credentials/'auth.json').read_bytes() == (personal/'auth.json').read_bytes()
    assert (credentials/'openrouter.key').read_text() == 'file-test-key'
    keyfile.unlink()
    only_oauth = tmp_path/'oauth'; only_oauth.mkdir()
    stage_credentials(only_oauth, ['gpt-test'])
    assert not (only_oauth/'openrouter.key').exists()


def test_missing_key_fails_without_starting_model(tmp_path, monkeypatch):
    monkeypatch.delenv('AVO_OPENROUTER_KEY_FILE', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    agent = CodexOAuthAgent(CodexOAuthConfig(model='openrouter/vendor/model'))
    with patch('avo.client.codex_oauth_agent._find_codex_bin', return_value='codex'), patch.object(
        IsolatedRuntime, 'preflight', return_value={'passed': True}
    ), patch.object(agent, '_run') as run:
        with pytest.raises(IsolationError, match='OpenRouter requires'):
            agent.run(object(), tmp_path/'workspace')
        run.assert_not_called()
