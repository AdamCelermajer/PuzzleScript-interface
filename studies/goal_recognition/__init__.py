from __future__ import annotations

import os

from client.engine.llm_client import Config


GOAL_RECOGNITION_MODEL = "openai/gpt-5.5"


def default_arc_api_key() -> str:
    """Read ARC key after the client LLM module has loaded the repo .env file."""
    return os.getenv("ARC_API_KEY", "")


def goal_recognition_config(
    *,
    backend_url: str,
    mode: str,
) -> Config:
    """Use the same OpenRouter config path as the main client engine."""
    return Config(
        server_url=backend_url,
        model=GOAL_RECOGNITION_MODEL,
        game="goal_recognition",
        mode=mode,
    )
