"""Harness picker data: ids, models, efforts and credential readiness.

Readiness only reports whether a credential or Docker object exists. Secret
values are never read into a response.
"""
from __future__ import annotations

import importlib
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from workbench.catalog import HARNESS_IDS, ROOT

EFFORTS = ["low", "medium", "high", "xhigh", "max"]
IMAGE = "puzzlescript-agents:local"
AGY_VOLUME = "puzzlescript-agy-home"

CODEX_MODELS = ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"]
CLAUDE_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]
ANTIGRAVITY_MODELS = ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low",
                      "claude-opus-5-5-low", "claude-opus-5-5-medium", "claude-opus-5-5-high",
                      "claude-sonnet-5-5-low", "claude-sonnet-5-5-medium", "claude-sonnet-5-5-high",
                      "gpt-oss-120b-medium"]

HARNESSES = {
    "codex": {"label": "Codex CLI", "providers": ["openai"]},
    "claude-code": {"label": "Claude Code", "providers": ["anthropic"]},
    "opencode": {"label": "OpenCode", "providers": ["openrouter", "nanogpt", "vast"]},
    "opencode-lean": {"label": "OpenCode lean", "providers": ["openrouter", "nanogpt", "vast"]},
    "antigravity": {"label": "Antigravity (agy)", "providers": ["google"]},
    "bare": {"label": "Bare tool loop", "providers": ["openrouter", "nanogpt"]},
}
# Harnesses that call a model API with a key from .env (harnesses/registry.py API_HARNESSES).
API_HARNESSES = {"opencode", "opencode-lean", "bare"}
PROVIDER_KEYS = {"openrouter": "OPENROUTER_API_KEY", "nanogpt": "NANOGPT_API_KEY"}
# Self-hosted vLLM (vast.ai): no key, no public catalog; its endpoint URL has a default.
KEYLESS_PROVIDERS = {"vast"}


def model_provider(model: str) -> str:
    """Provider implied by a model string (harness membership is checked separately)."""
    if model.startswith("openrouter/"):
        return "openrouter"
    if model.startswith("nanogpt/"):
        return "nanogpt"
    if model.startswith("vast/"):
        return "vast"
    if re.fullmatch(r"claude-[a-z]+-\d+(?:-\d+)*", model):
        return "anthropic"
    if model in ANTIGRAVITY_MODELS or re.fullmatch(r"(?:gemini|claude|gpt-oss)-[a-z0-9.-]+-(?:low|medium|high)", model):
        return "google"
    return "openai"


def model_error(harness: str, model: str) -> str | None:
    """None when `model` belongs to `harness`, else a readable reason."""
    if model.startswith("opencode/"):
        return "opencode/ model IDs are retired; use openrouter/vendor/model or nanogpt/model"
    if model.startswith("openrouter/"):
        native = model.removeprefix("openrouter/")
        if "/" not in native or any(not part for part in native.split("/")):
            return "Use openrouter/vendor/model for OpenRouter models"
    if model.startswith("nanogpt/") and any(not part for part in model.removeprefix("nanogpt/").split("/")):
        return "Use nanogpt/model with a model ID from the NanoGPT catalog"
    if model.startswith("vast/") and any(not part for part in model.removeprefix("vast/").split("/")):
        return "Use vast/<served-model-name> for the self-hosted vLLM"
    provider = model_provider(model)
    if provider not in HARNESSES[harness]["providers"]:
        return f"{model} is a {provider} model; {harness} runs {', '.join(HARNESSES[harness]['providers'])} models"
    return None


def env_keys(root: Path = ROOT) -> set[str]:
    """Names of non-empty variables in the project .env or the environment."""
    names = {name for name, value in os.environ.items() if value.strip()}
    try:
        for line in (root / ".env").read_text(encoding="utf-8-sig").splitlines():
            name, sep, value = line.partition("=")
            name = name.strip().removeprefix("export ").strip()
            if sep and not name.startswith("#") and value.strip().strip("'\""):
                names.add(name)
    except OSError:
        pass
    return names


_docker_cache: dict = {}
_docker_lock = Lock()


def docker_objects() -> dict:
    """Existence of the agent image and the Antigravity volume, cached for 30 s."""
    with _docker_lock:
        if _docker_cache and time.monotonic() - _docker_cache["at"] < 30:
            return _docker_cache["value"]

    def exists(*command: str) -> bool | None:
        try:
            return subprocess.run(["docker", *command], capture_output=True, timeout=8).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return None

    with ThreadPoolExecutor(2) as pool:
        image, volume = pool.map(lambda c: exists(*c), [("image", "inspect", IMAGE), ("volume", "inspect", AGY_VOLUME)])
    value = {"docker": image is not None, "image": bool(image), "agy_volume": bool(volume)}
    with _docker_lock:
        _docker_cache.update(at=time.monotonic(), value=value)
    return value


def registry_entries() -> tuple[dict, str | None]:
    """Optional overrides from `harnesses.registry`; tolerant of its exact shape."""
    try:
        registry = importlib.import_module("harnesses.registry")
    except Exception as exc:  # Absent or broken package: the picker still renders.
        return {}, f"{type(exc).__name__}: {exc}"
    source = None
    for name in ("HARNESSES", "REGISTRY", "harnesses"):
        source = getattr(registry, name, None)
        if source is not None:
            break
    if source is None:
        for name in ("list_harnesses", "all_harnesses"):
            if callable(getattr(registry, name, None)):
                source = getattr(registry, name)()
                break
    items = source.values() if isinstance(source, dict) else source or []
    entries = {}
    for item in items:
        data = item if isinstance(item, dict) else vars(item) if hasattr(item, "__dict__") else {}
        harness = data.get("id") or data.get("name")
        if harness in HARNESSES:
            entries[harness] = {k: data[k] for k in ("label", "providers", "efforts", "models") if data.get(k)}
    return entries, None


def _public_models(provider: str) -> tuple[list[dict], dict]:
    from workbench.model_catalog import catalog
    try:
        data = catalog(provider)
    except ValueError as exc:
        return [], {"provider": provider, "available": False, "warning": str(exc)}
    models = [{"id": m["id"], "label": m["name"], "provider": provider, "free": m["free"], "context": m["context"],
               "input_price": m["input_price"], "output_price": m["output_price"]} for m in data["models"]]
    return models, {"provider": provider, "available": True, "stale": data.get("stale", False),
                    "warning": data.get("warning")}


def harness_listing(root: Path = ROOT, include_public_catalogs: bool = True) -> list[dict]:
    keys = env_keys(root)
    docker = docker_objects()
    overrides, registry_error = registry_entries()
    public, catalogs = {}, []
    if include_public_catalogs:
        with ThreadPoolExecutor(2) as pool:
            for provider, (models, info) in zip(PROVIDER_KEYS, pool.map(_public_models, PROVIDER_KEYS)):
                public[provider] = models
                catalogs.append(info)
    codex_auth = (Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json").is_file()
    static_models = {"codex": [{"id": m, "label": m, "provider": "openai"} for m in CODEX_MODELS],
                     "claude-code": [{"id": m, "label": m, "provider": "anthropic"} for m in CLAUDE_MODELS],
                     "antigravity": [{"id": m, "label": m, "provider": "google"} for m in ANTIGRAVITY_MODELS]}
    result = []
    for harness in HARNESS_IDS:
        entry = {"id": harness, **HARNESSES[harness], "efforts": list(EFFORTS),
                 "models": static_models.get(harness) or [m for p in HARNESSES[harness]["providers"] for m in public.get(p, [])]}
        override = dict(overrides.get(harness, {}))
        if override.get("models"):
            # Union by id: registry entries first, then the workbench's known ids.
            known = {m["id"] for m in override["models"] if isinstance(m, dict) and m.get("id")}
            override["models"] = [m for m in override["models"] if isinstance(m, dict) and m.get("id")] + \
                [m for m in entry["models"] if m["id"] not in known]
        entry.update(override)
        missing = []
        if registry_error:
            missing.append("harnesses package")
        if not docker["docker"]:
            missing.append("docker (not reachable)")
        elif not docker["image"]:
            missing.append(f"docker image {IMAGE}")
        if harness == "codex" and not codex_auth:
            missing.append("~/.codex/auth.json (run codex login)")
        if harness == "claude-code" and "CLAUDE_CODE_OAUTH_TOKEN" not in keys:
            missing.append("CLAUDE_CODE_OAUTH_TOKEN in .env")
        if harness == "antigravity" and docker["docker"] and not docker["agy_volume"]:
            missing.append(f"docker volume {AGY_VOLUME} (run python -m harnesses.launch login antigravity)")
        if harness in API_HARNESSES:
            ready_providers = [p for p in entry["providers"] if p in KEYLESS_PROVIDERS or PROVIDER_KEYS.get(p) in keys]
            entry["ready_providers"] = ready_providers
            if not ready_providers:
                missing.append(" or ".join(f"{PROVIDER_KEYS[p]} in .env" for p in entry["providers"] if p in PROVIDER_KEYS))
        entry.update(ready=not missing, missing=missing, manual_model_ids=harness in API_HARNESSES,
                     provider_pin=harness in API_HARNESSES)
        if harness in API_HARNESSES:
            entry["model_catalogs"] = catalogs
        result.append(entry)
    return result
