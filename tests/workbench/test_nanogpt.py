import json
from unittest.mock import patch

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from avo.client.model_provider import api_key, resolve_model
from harnesses.chat import OpenRouterChat, ProviderError
from harnesses.launch import stage_credentials
from studies.codex_agent.session import GameSessionConfig
from workbench.catalog import agent_identity
from workbench.experiments import ExperimentRequest, create_router, plan_runs
from workbench.model_catalog import catalog, normalize


MODEL = "nanogpt/deepseek/deepseek-v4.1-flash"


@pytest.mark.parametrize("kind", ["avo", "codex"])
@pytest.mark.parametrize("harness", ["codex", "tools", "raw"])
def test_nanogpt_launch_preserves_provider_and_budgets(tmp_path, kind, harness):
    config = ExperimentRequest(kind=kind, agent_backend=harness, game_ids=["ps_sokoban_basic-v1"],
                               models=[MODEL], optimizer_model=MODEL, efforts=["max"], max_steps=123)
    row, = plan_runs(config, tmp_path / "output/workbench/job", tmp_path)
    assert row["model_provider"] == "nanogpt"
    assert row["command"][row["command"].index("--model" if kind == "codex" else "--player-model") + 1] == MODEL
    assert row["command"][row["command"].index("--harness") + 1] == harness
    if kind == "codex":
        assert row["command"][row["command"].index("--max-steps") + 1] == "123"
    identity = agent_identity({"harness": harness, "model": MODEL, "optimizer_model": MODEL})
    assert identity["model_provider"] == identity["optimizer_provider"] == "nanogpt"


def test_nanogpt_ids_and_unsupported_settings():
    assert resolve_model(MODEL) == ("nanogpt", "deepseek/deepseek-v4.1-flash")
    assert resolve_model("nanogpt/gpt-model") == ("nanogpt", "gpt-model")
    for model in ("nanogpt/", "nanogpt/vendor/", "nanogpt//model"):
        with pytest.raises(ValueError):
            resolve_model(model)
    for settings in ({"provider": "deepinfra"}, {"service_tier": "priority"}):
        with pytest.raises(ValueError):
            ExperimentRequest(kind="codex", game_ids=["a"], models=[MODEL], **settings)
    with pytest.raises(ValueError, match="pinning"):
        GameSessionConfig(model=MODEL, provider="deepinfra")


def test_catalog_keeps_nanogpt_per_million_prices_and_filters_non_tools():
    models = normalize("nanogpt", {"data": [
        {"id": "vendor/paid", "capabilities": {"tool_calling": True}, "context_length": 12345,
         "pricing": {"prompt": "0.25", "completion": "1.20", "unit": "per_million_tokens"}},
        {"id": "free", "capabilities": {"tool_calling": True}, "pricing": {"prompt": 0, "completion": 0}},
        {"id": "no-tools", "capabilities": {"tool_calling": False}},
        {"id": "unknown"},
    ]})
    paid = next(m for m in models if m["id"] == "nanogpt/vendor/paid")
    assert (paid["input_price"], paid["output_price"], paid["context"]) == (0.25, 1.20, 12345)
    assert len(models) == 2 and next(m for m in models if m["id"] == "nanogpt/free")["free"]
    router, = normalize("openrouter", {"data": [{"id": "vendor/model", "supported_parameters": ["tools"],
                                                  "pricing": {"prompt": "0.000001", "completion": "0.000002"}}]})
    assert (router["input_price"], router["output_price"]) == (1, 2)


def test_catalog_route_and_stale_cache_are_provider_specific(tmp_path):
    from workbench import model_catalog
    app = FastAPI()
    app.include_router(create_router(tmp_path))
    data = {"data": [{"id": "vendor/model", "capabilities": {"tool_calling": True}}]}
    with patch.dict(model_catalog._cache, {}, clear=True), patch("workbench.model_catalog.requests.get") as get:
        get.return_value.json.return_value = data
        response = TestClient(app).get("/api/workbench/model-catalog?provider=nanogpt")
        assert response.status_code == 200
        assert response.json()["models"][0]["id"] == "nanogpt/vendor/model"
        assert get.call_args.args[0] == "https://nano-gpt.com/api/v1/models?detailed=true"
        assert "headers" not in get.call_args.kwargs
        model_catalog._cache["nanogpt"]["fetched_at"] = 0
        get.side_effect = requests.Timeout()
        assert catalog("nanogpt")["stale"] is True
        with pytest.raises(ValueError, match="unavailable"):
            catalog("openrouter")


def test_nanogpt_chat_uses_own_key_endpoint_and_preserves_max(tmp_path, monkeypatch):
    monkeypatch.setenv("NANOGPT_API_KEY", "nano-test-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-test-secret")
    monkeypatch.delenv("AVO_NANOGPT_KEY_FILE", raising=False)
    reply = {"choices": [{"message": {"content": "ACTION1"}}], "usage": {"prompt_tokens": 12, "cost": 0.001}}
    with patch("dotenv.dotenv_values", return_value={}), patch("urllib.request.urlopen") as send:
        send.return_value.__enter__.return_value.read.return_value = json.dumps(reply).encode()
        chat = OpenRouterChat("vendor/model", "max", tmp_path, model_provider="nanogpt")
        message, record = chat.complete([{"role": "user", "content": "frame"}])
    request = send.call_args.args[0]
    assert request.full_url == "https://nano-gpt.com/api/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer nano-test-secret"
    body = json.loads(request.data)
    assert body["reasoning"]["effort"] == "max" and "usage" not in body and "provider" not in body
    assert message["content"] == "ACTION1" and record["model_provider"] == "nanogpt"
    assert chat.usage_totals["cost"] == 0.001
    for artifact in tmp_path.glob("*.json"):
        assert "test-secret" not in artifact.read_text()
    monkeypatch.delenv("NANOGPT_API_KEY")
    with patch("dotenv.dotenv_values", return_value={}):
        with pytest.raises(ProviderError, match="NANOGPT_API_KEY"):
            OpenRouterChat("vendor/model", "low", tmp_path, model_provider="nanogpt")


def test_nanogpt_credentials_stage_as_named_env_only(tmp_path):
    options, child_env = stage_credentials("bare", [MODEL], tmp_path, env={"NANOGPT_API_KEY": "project-secret",
                                                                         "OPENROUTER_API_KEY": "other"})
    assert options == ["--env", "NANOGPT_API_KEY"]
    assert child_env == {"NANOGPT_API_KEY": "project-secret"}
    assert "project-secret" not in str(options) and not list(tmp_path.iterdir())
