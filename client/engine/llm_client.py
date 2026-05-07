import os
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import litellm
from dotenv import load_dotenv

from client.engine.utils import extract_json

load_dotenv()


@dataclass
class Config:
    """Runtime configuration for server and model clients."""

    server_url: str = "http://localhost:3543"
    flash_model: str = "openai/gpt-oss-120b:nitro"
    pro_model: str = "openai/gpt-oss-120b:nitro"
    game: str = "ps_sokoban_basic-v1"
    mode: str = "learn"
    max_steps: int = 20
    show_legend: bool = False
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )
    rules_dir: str = field(
        default_factory=lambda: str(Path(__file__).resolve().parents[1] / "rules")
    )

    def __post_init__(self) -> None:
        """Validate required environment configuration."""
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY not found")


class LlmClient:
    """Wrapper around litellm with model-specific routing parameters."""

    def __init__(
        self,
        config: Config,
        event_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize provider credentials and runtime config."""
        self.cfg = config
        self.event_sink = event_sink
        os.environ["OPENROUTER_API_KEY"] = config.openrouter_api_key

    def _log(self, message: str) -> None:
        if self.event_sink is not None:
            self.event_sink(message)
            return
        print(message)

    def _call(
        self,
        system: str,
        prompt: str,
        model_type: str = "flash",
        json_mode: bool = False,
    ) -> str:
        """Call the configured OpenRouter model and return plain text output."""
        litellm_model = self._litellm_model(model_type)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        kwargs["timeout"] = 45
        self._log(f"Asking {litellm_model}...")
        start = time.time()
        response = litellm.completion(
            model=litellm_model,
            messages=messages,
            **kwargs,
        )
        self._log(f"[{litellm_model}] Response time: {time.time() - start:.1f}s")
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ValueError("LLM returned empty content")
        return content.strip()

    def call_text(
        self,
        system: str,
        prompt: str,
        model_type: str = "flash",
    ) -> str:
        return self._call(system, prompt, model_type=model_type, json_mode=False)

    def call_json(
        self,
        system: str,
        prompt: str,
        model_type: str = "flash",
    ) -> dict:
        response = self._call(system, prompt, model_type=model_type, json_mode=True)
        try:
            data = json.loads(extract_json(response))
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("LLM JSON response must be an object")
        return data

    def _model_name(self, model_type: str) -> str:
        return self.cfg.pro_model if model_type == "pro" else self.cfg.flash_model

    def _litellm_model(self, model_type: str) -> str:
        model_name = self._model_name(model_type)
        if model_name.startswith("openrouter/"):
            return model_name
        return f"openrouter/{model_name}"
