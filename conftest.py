"""Shared pytest setup: tests never reach provider APIs."""
import pytest


@pytest.fixture(autouse=True)
def _no_provider_model_lists(monkeypatch):
    # harnesses.opencode looks up image input in the provider's model list at session start.
    monkeypatch.setattr("harnesses.opencode._model_list", lambda provider: {})
