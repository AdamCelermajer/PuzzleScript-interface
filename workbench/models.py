from __future__ import annotations

from typing import Any


PROVIDER_ID = "openrouter"
PROVIDER_LABEL = "OpenRouter"
DEFAULT_MODEL = "anthropic/claude-opus-4.8"
CODEX_PROVIDER_ID = "codex_oauth"
CODEX_PROVIDER_LABEL = "Codex OAuth"
DEFAULT_CODEX_MODEL = "gpt-5.6-sol"

MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": DEFAULT_MODEL,
        "label": "Anthropic: Claude Opus 4.8",
        "supported_efforts": ["max", "xhigh", "high", "medium", "low"],
        "default_effort": "medium",
        "reasoning_mandatory": False,
    },
    {
        "id": "openai/gpt-5.6-luna",
        "label": "OpenAI: GPT-5.6 Luna",
        "supported_efforts": ["max", "xhigh", "high", "medium", "low", "none"],
        "default_effort": "medium",
        "reasoning_mandatory": False,
    },
    {
        "id": "x-ai/grok-4.5",
        "label": "xAI: Grok 4.5",
        "supported_efforts": ["high", "medium", "low"],
        "default_effort": "high",
        "reasoning_mandatory": True,
    },
    {
        "id": "xiaomi/mimo-v2.5",
        "label": "Xiaomi: MiMo-V2.5",
        "supported_efforts": [],
        "default_effort": "",
        "reasoning_mandatory": False,
    },
)

MODEL_BY_ID = {item["id"]: item for item in MODEL_CATALOG}

CODEX_MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": DEFAULT_CODEX_MODEL,
        "label": "OpenAI: GPT-5.6 Sol",
        "supported_efforts": ["minimal", "low", "medium", "high", "xhigh"],
        "default_effort": "low",
        "reasoning_mandatory": True,
    },
)
CODEX_MODEL_BY_ID = {item["id"]: item for item in CODEX_MODEL_CATALOG}


def validate_model_selection(model: str, reasoning_effort: str) -> None:
    details = MODEL_BY_ID.get(model)
    if details is None:
        raise ValueError("model is not available in the workbench")
    if reasoning_effort and reasoning_effort not in details["supported_efforts"]:
        raise ValueError("reasoning_effort is not supported by the selected model")


def validate_codex_model_selection(model: str, reasoning_effort: str) -> None:
    details = CODEX_MODEL_BY_ID.get(model)
    if details is None:
        raise ValueError("Codex model is not available in the workbench")
    if reasoning_effort not in details["supported_efforts"]:
        raise ValueError("reasoning_effort is not supported by the Codex model")


def public_model_catalog() -> dict[str, Any]:
    return {
        "provider": {"id": PROVIDER_ID, "label": PROVIDER_LABEL},
        "default_model": DEFAULT_MODEL,
        "models": [dict(item) for item in MODEL_CATALOG],
        "codex": {
            "provider": {
                "id": CODEX_PROVIDER_ID,
                "label": CODEX_PROVIDER_LABEL,
            },
            "default_model": DEFAULT_CODEX_MODEL,
            "models": [dict(item) for item in CODEX_MODEL_CATALOG],
        },
    }
