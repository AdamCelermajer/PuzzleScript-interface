"""Public model catalogs for the picker. Never reads or returns credentials."""
from __future__ import annotations

import time
import math
import re
from threading import Lock

import requests

_cache: dict = {}
_lock = Lock()
URLS = {"openrouter": "https://openrouter.ai/api/v1/models"}


def normalize(provider: str, data: dict) -> list[dict]:
    if provider not in URLS:
        raise ValueError("Only the OpenRouter public catalog is supported")
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Invalid model catalog")
    result = []
    for model in data.get("data", []):
        if not isinstance(model, dict):
            continue
        name = model.get("id", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,148}", name) or name.endswith(":batch"):
            continue
        if "tools" not in (model.get("supported_parameters") or []):
            continue
        prices = model.get("pricing") or {}
        def price(key):
            try:
                value = float(prices[key]) * 1_000_000
                return value if value >= 0 and math.isfinite(value) else None
            except (KeyError, TypeError, ValueError):
                return None
        incoming, outgoing = price("prompt"), price("completion")
        result.append({"id": f"openrouter/{name}", "name": model.get("name") or name,
                       "provider": provider, "free": incoming == 0 and outgoing == 0,
                       "context": model.get("context_length"), "input_price": incoming, "output_price": outgoing})
    return sorted(result, key=lambda m: m["name"].lower())


def catalog(provider: str) -> dict:
    if provider not in URLS:
        raise ValueError("Only the OpenRouter public catalog is supported")
    with _lock:
        cached = _cache.get(provider)
        if cached and time.time() - cached["fetched_at"] < 600:
            return cached
    try:
        response = requests.get(URLS[provider], timeout=12)
        response.raise_for_status()
        models = normalize(provider, response.json())
        if not models:
            raise ValueError("Provider returned no compatible models")
        value = {"provider": provider, "models": models, "fetched_at": time.time(), "stale": False}
        with _lock:
            _cache[provider] = value
        return value
    except (requests.RequestException, ValueError):
        if cached:
            return {**cached, "stale": True, "warning": "Catalog refresh failed. Showing the last fetched list."}
        raise ValueError("Model catalog is unavailable. Retry or enter a model ID manually.") from None
