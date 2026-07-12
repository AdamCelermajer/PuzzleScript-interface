from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from client.engine.utils import extract_json

load_dotenv()


@dataclass
class ReactLlmConfig:
    """Kimi configuration scoped to the ReAct experiment."""

    model: str = "kimi-k2.6"
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "REACT_AGENT_KIMI_BASE_URL",
            "https://api.kimi.com/coding/v1",
        )
    )
    max_tokens: int = 4096
    disable_thinking: bool = True
    kimi_api_key: str = field(
        default_factory=lambda: (
            os.getenv("REACT_AGENT_KIMI_API_KEY", "")
            or os.getenv("REACT_AGENT_MOONSHOT_API_KEY", "")
        )
    )

    def __post_init__(self) -> None:
        if not self.kimi_api_key:
            raise ValueError(
                "REACT_AGENT_KIMI_API_KEY or REACT_AGENT_MOONSHOT_API_KEY not found"
            )


class ReactLlmClient:
    """Small Kimi client owned by the ReAct experiment."""

    def __init__(
        self,
        config: ReactLlmConfig,
        event_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.cfg = config
        self.event_sink = event_sink
        self.client = OpenAI(
            base_url=config.base_url,
            api_key=config.kimi_api_key,
        )

    def _log(self, message: str) -> None:
        print(message)
        if self.event_sink is not None:
            self.event_sink(message)

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
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("LLM JSON response must be an object")
        return data

    def _call(
        self,
        system: str,
        prompt: str,
        *,
        json_mode: bool,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> str:
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
        if self.cfg.disable_thinking:
            kwargs["extra_body"] = {
                "thinking": {"type": "disabled"},
            }
        if self.cfg.max_tokens:
            kwargs["max_tokens"] = self.cfg.max_tokens

        model = self.model_id()
        purpose_text = f" for {purpose}" if purpose else ""
        self._log(f"Asking {model}{purpose_text}...")
        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs,
            )
        except OpenAIError as exc:
            raise ValueError(f"LLM provider error: {exc}") from exc
        self._log(f"[{model}] Response time: {time.time() - start:.1f}s")
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ValueError("LLM returned empty content")
        return content.strip()

    def model_id(self) -> str:
        if self.cfg.model.startswith("moonshot/"):
            return self.cfg.model[len("moonshot/") :]
        return self.cfg.model
