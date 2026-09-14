"""Explicit provider-qualified model IDs for the existing Codex runner."""
from __future__ import annotations


def resolve_model(model: str) -> tuple[str, str]:
    if model.startswith("openrouter/"):
        native = model.removeprefix("openrouter/")
        if "/" not in native or any(not part for part in native.split("/")):
            raise ValueError("Use openrouter/vendor/model for OpenRouter models")
        return "openrouter", native
    if model.startswith("opencode/"):
        raise ValueError("OpenCode is retired; use a Codex model or openrouter/vendor/model")
    return "openai", model
