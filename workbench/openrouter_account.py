from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import set_key


KEY_STATUS_URL = "https://openrouter.ai/api/v1/key"


def default_env_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def get_status(api_key: str | None = None) -> dict[str, Any]:
    key = (api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")).strip()
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not key:
        return {
            "configured": False,
            "state": "not_configured",
            "api_key": "",
            "checked_at": checked_at,
        }

    try:
        response = requests.get(
            KEY_STATUS_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
    except requests.RequestException:
        return {
            "configured": True,
            "state": "unreachable",
            "api_key": key,
            "checked_at": checked_at,
        }

    if response.status_code != 200:
        states = {
            401: "invalid",
            402: "insufficient_credits",
            403: "forbidden",
            429: "rate_limited",
        }
        return {
            "configured": True,
            "state": states.get(response.status_code, "unavailable"),
            "api_key": key,
            "status_code": response.status_code,
            "checked_at": checked_at,
        }

    try:
        payload = response.json()
    except ValueError:
        return {
            "configured": True,
            "state": "unavailable",
            "api_key": key,
            "status_code": response.status_code,
            "checked_at": checked_at,
        }
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    remaining = _number_or_none(data.get("limit_remaining"))
    expires_at = data.get("expires_at")
    state = "usable"
    if remaining is not None and remaining <= 0:
        state = "limit_exhausted"
    elif _is_expired(expires_at):
        state = "expired"

    return {
        "configured": True,
        "state": state,
        "api_key": key,
        "label": str(data.get("label", "")),
        "limit": _number_or_none(data.get("limit")),
        "limit_remaining": remaining,
        "limit_reset": data.get("limit_reset"),
        "usage": _number_or_zero(data.get("usage")),
        "usage_daily": _number_or_zero(data.get("usage_daily")),
        "usage_weekly": _number_or_zero(data.get("usage_weekly")),
        "usage_monthly": _number_or_zero(data.get("usage_monthly")),
        "is_free_tier": bool(data.get("is_free_tier", False)),
        "expires_at": expires_at,
        "checked_at": checked_at,
    }


def replace_key(api_key: str, env_path: str | Path | None = None) -> dict[str, Any]:
    key = api_key.strip()
    status = get_status(key)
    if status["state"] != "usable":
        raise ValueError(f"OpenRouter key is not usable: {status['state']}")
    target = Path(env_path or default_env_path())
    target.touch(exist_ok=True)
    set_key(str(target), "OPENROUTER_API_KEY", key, quote_mode="never")
    os.environ["OPENROUTER_API_KEY"] = key
    return status


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number_or_zero(value: object) -> float:
    return _number_or_none(value) or 0.0


def _is_expired(value: object) -> bool:
    if not value:
        return False
    try:
        expires_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return expires_at <= datetime.now(timezone.utc)
