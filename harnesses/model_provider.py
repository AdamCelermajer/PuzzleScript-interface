"""Provider-qualified model ids shared by the harnesses and the workbench."""
from __future__ import annotations

import os
from pathlib import Path

VAST_BASE_URL = "http://host.docker.internal:18100/v1"
API_PROVIDERS = {
    "openrouter": {"label": "OpenRouter", "origin": "https://openrouter.ai", "env_key": "OPENROUTER_API_KEY"},
    "nanogpt": {"label": "NanoGPT", "origin": "https://nano-gpt.com", "env_key": "NANOGPT_API_KEY"},
    # Self-hosted vLLM on a rented vast.ai machine, behind an SSH tunnel on the host
    # (docs/research/vast-setup-20261021.md). Its variable is the endpoint, not a secret.
    "vast": {"label": "vast.ai vLLM", "origin": VAST_BASE_URL, "env_key": "VAST_LLM_BASE_URL", "default": VAST_BASE_URL},
}


def api_key(provider: str, *, env_file: Path | None = None) -> str:
    details = API_PROVIDERS[provider]
    file_var = f"AVO_{provider.upper()}_KEY_FILE"
    key_file = os.environ.get(file_var, "")
    if key_file:
        key = Path(key_file).read_text(encoding="utf-8").strip()
    else:
        key = ""
        if env_file is not None and env_file.is_file():
            from dotenv import dotenv_values
            key = str(dotenv_values(env_file).get(details["env_key"]) or "").strip()
        key = key or os.environ.get(details["env_key"], "").strip()
    if not key:
        raise RuntimeError(f"{details['label']} requires an existing {details['env_key']} or {file_var}")
    return key


def resolve_model(model: str) -> tuple[str, str]:
    if model.startswith("nanogpt/"):
        native = model.removeprefix("nanogpt/")
        if not native or any(not part for part in native.split("/")):
            raise ValueError("Use nanogpt/model with a model ID from the NanoGPT catalog")
        return "nanogpt", native
    if model.startswith("vast/"):
        native = model.removeprefix("vast/")
        if not native or any(not part for part in native.split("/")):
            raise ValueError("Use vast/<served-model-name> for the self-hosted vLLM")
        return "vast", native
    if model.startswith("openrouter/"):
        native = model.removeprefix("openrouter/")
        if "/" not in native or any(not part for part in native.split("/")):
            raise ValueError("Use openrouter/vendor/model for OpenRouter models")
        return "openrouter", native
    if model.startswith("opencode/"):
        raise ValueError("opencode/ model ids are retired; use openrouter/vendor/model or nanogpt/model")
    return "openai", model
