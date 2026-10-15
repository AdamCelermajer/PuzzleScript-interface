"""Explicit provider-qualified model IDs for the existing Codex runner."""
from __future__ import annotations

import os
from pathlib import Path

API_PROVIDERS = {
    "openrouter": {"label": "OpenRouter", "origin": "https://openrouter.ai", "env_key": "OPENROUTER_API_KEY"},
    "nanogpt": {"label": "NanoGPT", "origin": "https://nano-gpt.com", "env_key": "NANOGPT_API_KEY"},
}


def api_key(provider: str, *, env_file: Path | None = None) -> str:
    details = API_PROVIDERS[provider]
    file_var = f"AVO_{provider.upper()}_KEY_FILE"
    key_file = os.environ.get(file_var, "")
    if key_file:
        key = Path(key_file).read_text(encoding="utf-8").strip()
    else:
        key = ""
        if env_file is not None:
            from dotenv import dotenv_values
            key = str(dotenv_values(env_file).get(details["env_key"]) or "").strip()
        key = key or os.environ.get(details["env_key"], "").strip()
    if not key:
        raise RuntimeError(f"{details['label']} requires an existing {details['env_key']} or {file_var}")
    return key


def codex_provider_overrides(provider: str, base_url: str) -> list[str]:
    details = API_PROVIDERS[provider]
    prefix = f"model_providers.{provider}"
    return [f'model_provider="{provider}"', f'{prefix}.name="{details["label"]}"',
            f'{prefix}.base_url="{base_url}"', f'{prefix}.env_key="{details["env_key"]}"',
            f'{prefix}.wire_api="responses"', f'{prefix}.requires_openai_auth=false']


def resolve_model(model: str) -> tuple[str, str]:
    if model.startswith("nanogpt/"):
        native = model.removeprefix("nanogpt/")
        if not native or any(not part for part in native.split("/")):
            raise ValueError("Use nanogpt/model with a model ID from the NanoGPT catalog")
        return "nanogpt", native
    if model.startswith("openrouter/"):
        native = model.removeprefix("openrouter/")
        if "/" not in native or any(not part for part in native.split("/")):
            raise ValueError("Use openrouter/vendor/model for OpenRouter models")
        return "openrouter", native
    if model.startswith("opencode/"):
        raise ValueError("OpenCode is retired; use a Codex model or openrouter/vendor/model")
    return "openai", model
