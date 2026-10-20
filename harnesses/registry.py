"""Harness ids, providers, model validation, credentials and readiness (contract section 1).

``list_harnesses()`` is the function the workbench calls; ``HARNESSES`` is the same
static data keyed by id. Credential checks only test presence, never read values
into results.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from harnesses.model_provider import API_PROVIDERS, resolve_model
from harnesses.base import EFFORTS, CliSession, HarnessError

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "puzzlescript-agents:local"
AGY_VOLUME = "puzzlescript-agy-home"
HARNESS_IDS = ("codex", "claude-code", "opencode", "antigravity", "bare")

CODEX_MODELS = ("gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra", "gpt-5.5", "gpt-5.3-codex-spark")
CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1")
# `agy models` needs a login; these are the ids seen on 2026-10-15.
ANTIGRAVITY_MODELS = ("gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low")
# Known-good defaults; the workbench supplies the full public catalogs through ``models_hook``.
API_MODELS = ("openrouter/qwen/qwen3.8-27b", "openrouter/deepseek/deepseek-v4.1-flash",
              "nanogpt/deepseek/deepseek-v4.1-flash")

EFFORT_FLAGS = {
    "codex": "-c model_reasoning_effort=<effort>",
    "claude-code": "--effort <effort>",
    "opencode": "--variant <effort> (max -> xhigh)",
    "antigravity": "--effort <effort>",
    "bare": "reasoning.effort=<effort> (OpenRouter: max -> xhigh)",
}
WEB_TOOLS = {
    "codex": 'web_search="disabled", features.browser_use/computer_use/apps/plugins=false',
    "claude-code": "--disallowedTools WebSearch WebFetch",
    "opencode": "opencode.json permission webfetch/websearch/codesearch = deny",
    "antigravity": "global PreToolUse hook denies search_web/read_url_content/browser_* (~/.gemini/config/hooks.json)",
    "bare": "no web tools exist (shell/read_file/write_file/view_image only)",
}

HARNESSES: dict[str, dict[str, Any]] = {
    "codex": {"id": "codex", "label": "Codex CLI", "providers": ["openai"], "cli": "codex exec --json",
              "models": [{"id": m, "label": m} for m in CODEX_MODELS]},
    "claude-code": {"id": "claude-code", "label": "Claude Code", "providers": ["anthropic"],
                    "cli": "claude -p --output-format stream-json --verbose",
                    "models": [{"id": m, "label": m} for m in CLAUDE_MODELS]},
    "opencode": {"id": "opencode", "label": "OpenCode", "providers": ["openrouter", "nanogpt"],
                 "cli": "opencode run --format json", "models": []},
    "antigravity": {"id": "antigravity", "label": "Antigravity (agy)", "providers": ["google"],
                    "cli": "agy -p --output-format stream-json",
                    "models": [{"id": m, "label": m} for m in ANTIGRAVITY_MODELS]},
    "bare": {"id": "bare", "label": "Bare tool loop", "providers": ["openrouter", "nanogpt"],
             "cli": "in-process chat completions + shell/read/write/view_image tools", "models": []},
}
for _id, _entry in HARNESSES.items():
    _entry["efforts"] = list(EFFORTS)
    _entry["effort_flag"] = EFFORT_FLAGS[_id]
    _entry["web_tools"] = WEB_TOOLS[_id]


def resolve_model_for(harness: str, model: str) -> tuple[str, str]:
    """Return (provider, native model id) or raise HarnessError if the harness cannot run it."""
    if harness not in HARNESSES:
        raise HarnessError(f"Unknown harness {harness!r}; use one of {', '.join(HARNESS_IDS)}")
    model = str(model or "").strip()
    if not model:
        raise HarnessError("A model id is required")
    if harness == "claude-code":
        if not model.startswith("claude-") or "/" in model:
            raise HarnessError("claude-code runs Anthropic model ids such as claude-sonnet-5-5")
        return "anthropic", model
    if harness == "antigravity":
        if "/" in model:
            raise HarnessError("antigravity runs ids from `agy models`, e.g. gemini-3.8-flash-high")
        return "google", model
    try:
        provider, native = resolve_model(model)
    except ValueError as exc:
        raise HarnessError(str(exc)) from None
    if harness == "codex":
        if provider != "openai" or model.startswith("claude-") or "/" in model:
            raise HarnessError("codex runs OpenAI model ids such as gpt-5.6-sol (ChatGPT login)")
        return "openai", native
    if provider not in API_PROVIDERS:
        raise HarnessError(f"{harness} runs openrouter/<vendor>/<model> or nanogpt/<model> ids")
    return provider, native


def session_class(harness: str) -> type[CliSession]:
    if harness == "codex":
        from harnesses.codex import CodexSession as cls
    elif harness == "claude-code":
        from harnesses.claude_code import ClaudeCodeSession as cls
    elif harness == "opencode":
        from harnesses.opencode import OpenCodeSession as cls
    elif harness == "antigravity":
        from harnesses.antigravity import AntigravitySession as cls
    elif harness == "bare":
        from harnesses.bare import BareSession as cls
    else:
        raise HarnessError(f"Unknown harness {harness!r}")
    return cls


def create_session(harness: str) -> CliSession:
    return session_class(harness)()


def credentials_for(harness: str, models: list[str]) -> list[str]:
    """Credential names a run needs: env var names, ``codex-auth`` or ``agy-volume``."""
    if harness == "codex":
        return ["codex-auth"]
    if harness == "claude-code":
        return ["CLAUDE_CODE_OAUTH_TOKEN"]
    if harness == "antigravity":
        return ["agy-volume"]
    providers = sorted({resolve_model_for(harness, model)[0] for model in models})
    return [API_PROVIDERS[provider]["env_key"] for provider in providers]


def env_values(env_file: Path | None = None) -> dict[str, str]:
    """Non-empty variables from the project .env, overridden by the process environment."""
    values: dict[str, str] = {}
    path = env_file or ROOT / ".env"
    if path.is_file():
        from dotenv import dotenv_values
        values.update({key: str(value).strip() for key, value in dotenv_values(path).items() if value and str(value).strip()})
    values.update({key: value.strip() for key, value in os.environ.items() if value.strip()})
    return values


def codex_auth_path() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"


def codex_auth_ready() -> bool:
    try:
        return bool(json.loads(codex_auth_path().read_text(encoding="utf-8")).get("tokens"))
    except (OSError, ValueError):
        return False


def docker_object_exists(kind: str, name: str) -> bool | None:
    """True/False, or None when Docker is unreachable."""
    try:
        result = subprocess.run(["docker", kind, "inspect", name], stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    stderr = (result.stderr or "").lower()
    if result.returncode and ("cannot connect" in stderr or "error during connect" in stderr):
        return None
    return result.returncode == 0


def missing_credentials(harness: str, *, env: dict[str, str] | None = None, providers: list[str] | None = None,
                        agy_volume: bool | None = None) -> list[str]:
    values = env if env is not None else env_values()
    missing: list[str] = []
    if harness == "codex" and not codex_auth_ready():
        missing.append(f"{codex_auth_path()} with a ChatGPT login (run `codex login`)")
    if harness == "claude-code" and not values.get("CLAUDE_CODE_OAUTH_TOKEN"):
        missing.append("CLAUDE_CODE_OAUTH_TOKEN in .env (create with `claude setup-token`)")
    if harness in {"opencode", "bare"}:
        wanted = providers or HARNESSES[harness]["providers"]
        keys = [API_PROVIDERS[provider]["env_key"] for provider in wanted]
        present = [key for key in keys if values.get(key)]
        if (providers and len(present) != len(keys)) or not present:
            missing.append(" and ".join(f"{key} in .env" for key in keys if not values.get(key)))
    if harness == "antigravity" and agy_volume is False:
        missing.append(f"docker volume {AGY_VOLUME} (run `uv run python -m harnesses.launch login antigravity`)")
    return missing


def list_harnesses(*, models_hook: Callable[[str], list[dict]] | None = None, check_docker: bool = False,
                   env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """[{id, label, providers, models:[{id,label}], efforts, ready, missing}] (contract section 4).

    ``models_hook(provider)`` supplies catalog models for opencode/bare (e.g. the
    workbench's OpenRouter/NanoGPT catalogs); otherwise a short default list is used.
    ``check_docker`` also checks the image and the Antigravity volume (slow).
    """
    values = env if env is not None else env_values()
    image = docker_object_exists("image", IMAGE) if check_docker else None
    volume = docker_object_exists("volume", AGY_VOLUME) if check_docker else None
    listing = []
    for harness in HARNESS_IDS:
        entry = {key: (list(value) if isinstance(value, list) else value) for key, value in HARNESSES[harness].items()}
        if harness in {"opencode", "bare"}:
            models: list[dict] = []
            for provider in entry["providers"]:
                if models_hook is not None:
                    models += [{"id": item["id"], "label": item.get("label") or item.get("name") or item["id"]}
                               for item in models_hook(provider)]
            entry["models"] = models or [{"id": m, "label": m} for m in API_MODELS]
        missing = missing_credentials(harness, env=values, agy_volume=volume)
        if check_docker and image is None:
            missing.append("docker (not reachable)")
        elif check_docker and image is False:
            missing.append(f"docker image {IMAGE} (docker build -t {IMAGE} harnesses/docker)")
        entry.update(ready=not missing, missing=missing)
        listing.append(entry)
    return listing
