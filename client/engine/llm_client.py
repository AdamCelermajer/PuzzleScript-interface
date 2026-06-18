import os
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI
from dotenv import load_dotenv

from client.engine.utils import extract_json

load_dotenv()


@dataclass
class Config:
    """Runtime configuration for server and model clients."""

    server_url: str = "http://localhost:3543"
    model: str = "anthropic/claude-opus-4.8"
    # reasoning_effort is sent to the model only when non-empty.
    # Use "low"/"medium"/"high" only if the chosen model supports it.
    reasoning_effort: str = ""
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
    """Direct OpenRouter client via the OpenAI-compatible API."""

    def __init__(
        self,
        config: Config,
        event_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize OpenRouter credentials and runtime config."""
        self.cfg = config
        self.event_sink = event_sink
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter_api_key,
        )

    def _log(self, message: str) -> None:
        print(message)
        if self.event_sink is not None:
            self.event_sink(message)

    def _call(
        self,
        system: str,
        prompt: str,
        json_mode: bool = False,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> str:
        """Call the configured OpenRouter model and return plain text output."""
        user_content: str | list[dict] = prompt
        images = [url for url in image_data_urls or [] if str(url).strip()]
        if images:
            user_content = [
                {"type": "text", "text": prompt},
                *[
                    {"type": "image_url", "image_url": {"url": str(url)}}
                    for url in images
                ],
            ]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        kwargs: dict = {"timeout": 45}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.cfg.reasoning_effort:
            kwargs["reasoning_effort"] = self.cfg.reasoning_effort

        model = self._openrouter_model()
        purpose_text = f" for {purpose}" if purpose else ""
        self._log(f"Asking {model}{purpose_text}...")
        start = time.time()
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        self._log(f"[{model}] Response time: {time.time() - start:.1f}s")
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ValueError("LLM returned empty content")
        return content.strip()

    def call_text(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> str:
        return self._call(
            system,
            prompt,
            json_mode=False,
            image_data_urls=image_data_urls,
            purpose=purpose,
        )

    def call_json(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> dict:
        response = self._call(
            system,
            prompt,
            json_mode=True,
            image_data_urls=image_data_urls,
            purpose=purpose,
        )
        try:
            data = json.loads(extract_json(response))
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("LLM JSON response must be an object")
        return data

    def _openrouter_model(self) -> str:
        """Return the bare OpenRouter model ID (strip litellm-style prefix)."""
        if self.cfg.model.startswith("openrouter/"):
            return self.cfg.model[len("openrouter/"):]
        return self.cfg.model
