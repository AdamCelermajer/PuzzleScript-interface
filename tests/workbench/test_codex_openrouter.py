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


@pytest.mark.parametrize('overrides', [
    {'kind': 'codex'}, {'service_tier': 'priority'},
    {'models': ['openrouter/deepseek']}, {'optimizer_model': 'opencode/muse'},
])
def test_rejects_unsupported_combinations(overrides):
    with pytest.raises(ValueError):
        request(**overrides)
