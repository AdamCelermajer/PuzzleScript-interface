from studies.goal_recognition.keys import (
    GOAL_RECOGNITION_MODEL,
    default_arc_api_key,
    goal_recognition_config,
)


def test_default_arc_api_key_reads_environment_after_client_dotenv_load(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARC_API_KEY", "arc-test-key")

    assert default_arc_api_key() == "arc-test-key"


def test_goal_recognition_config_uses_client_openrouter_config(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test-key")

    config = goal_recognition_config(
        backend_url="https://three.arcprize.org",
        mode="one_frame",
    )

    assert config.server_url == "https://three.arcprize.org"
    assert config.game == "goal_recognition"
    assert config.mode == "one_frame"
    assert config.model == GOAL_RECOGNITION_MODEL
    assert config.model == "openai/gpt-5.5"
    assert config.reasoning_effort == "low"
    assert config.openrouter_api_key == "openrouter-test-key"
