import pytest
from workbench.experiments import ExperimentRequest, plan_runs
from workbench.catalog import agent_identity


def request(**overrides):
    return ExperimentRequest(**{**dict(kind='avo', agent_backend='codex', game_ids=['ps_sokoban_basic-v1'],
        models=['openrouter/deepseek/deepseek-v4.1-flash'], optimizer_model='gpt-6-astra',
        efforts=['low'], optimizer_effort='low'), **overrides})


def test_qualified_models_use_existing_launcher_and_preserve_provenance(tmp_path):
    row, = plan_runs(request(), tmp_path/'output/workbench/test', tmp_path)
    assert row['command'][1:3] == ['-m', 'avo.docker.launch']
    assert row['agent_backend'] == 'codex'
    assert row['model_provider'] == 'openrouter'
    assert row['model'] == 'openrouter/deepseek/deepseek-v4.1-flash'
    assert row['optimizer_model'] == 'gpt-6-astra'
    identity = agent_identity({'player': {'model': row['model']}, 'optimizer_model': row['model']})
    assert identity['agent_backend'] == 'codex'
    assert identity['model_provider'] == identity['optimizer_provider'] == 'openrouter'


def test_openrouter_direct_player_plan_preserves_baseline_plus_budget_and_max(tmp_path):
    row, = plan_runs(request(kind='codex', models=['openrouter/qwen/qwen3.8-27b'],
                            efforts=['max'], conditions=['baseline-plus'], max_steps=500),
                    tmp_path/'output/workbench/test', tmp_path)
    command = row['command']
    assert command[1:3] == ['-m', 'studies.codex_agent.run']
    assert command[command.index('--model')+1] == 'openrouter/qwen/qwen3.8-27b'
    assert command[command.index('--effort')+1] == 'max'
    assert command[command.index('--condition')+1] == 'baseline-plus'
    assert command[command.index('--max-steps')+1] == '500'
    assert row['model_provider'] == 'openrouter'


@pytest.mark.parametrize('overrides', [
    {'service_tier': 'priority'},
    {'models': ['openrouter/deepseek']}, {'optimizer_model': 'opencode/muse'},
])
def test_rejects_unsupported_combinations(overrides):
    with pytest.raises(ValueError):
        request(**overrides)


@pytest.mark.parametrize('harness', ['tools', 'raw'])
def test_harness_ladder_reaches_both_launchers_and_catalog(tmp_path, harness):
    avo, = plan_runs(request(agent_backend=harness, optimizer_model='openrouter/qwen/qwen3.8-27b'),
                     tmp_path/'output/workbench/a', tmp_path)
    assert avo['command'][avo['command'].index('--harness')+1] == harness
    direct, = plan_runs(request(kind='codex', agent_backend=harness, conditions=['baseline-plus']),
                        tmp_path/'output/workbench/b', tmp_path)
    assert direct['command'][direct['command'].index('--harness')+1] == harness
    assert agent_identity({'harness': harness, 'model': 'openrouter/a/b'})['agent_backend'] == harness


def test_non_codex_harness_rejects_codex_login_models():
    with pytest.raises(ValueError, match='OpenRouter'):
        request(agent_backend='tools')  # optimizer gpt-6-astra is a Codex-login model


def test_pinned_provider_reaches_both_launchers(tmp_path):
    for kind in ('avo', 'codex'):
        row, = plan_runs(request(kind=kind, provider='deepinfra', optimizer_model='openrouter/qwen/qwen3.8-27b'),
                         tmp_path/'output/workbench'/kind, tmp_path)
        assert row['command'][row['command'].index('--provider')+1] == 'deepinfra'
        assert row['provider'] == 'deepinfra'
