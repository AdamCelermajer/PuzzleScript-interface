import os
import time
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import litellm
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Runtime configuration for server and model clients."""

    server_url: str = "http://localhost:3000"
    flash_model: str = "gemini-3-flash-preview"
    pro_model: str = "gemini-3.1-pro-preview"
    game: str = "sokoban-basic"
    mode: str = "learn"
    max_steps: int = 20
    show_legend: bool = False
    api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    rules_dir: str = "rules"

    def __post_init__(self) -> None:
        """Validate required environment configuration."""
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found")


class LlmClient:
    """Wrapper around litellm with model-specific routing parameters."""

    MAX_RETRIES = 5
    CIRCUIT_BREAKER_COOLDOWN = 60

    def __init__(
        self,
        config: Config,
        event_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize provider credentials and runtime config."""
        self.cfg = config
        self.event_sink = event_sink
        self.consecutive_failures = 0
        self.circuit_breaker_until = 0.0
        os.environ["GEMINI_API_KEY"] = config.api_key

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
        """Call the configured LLM and return plain text output.

        Retries up to MAX_RETRIES times with backoff. After MAX_RETRIES
        consecutive failures, raises so the caller can skip the turn or abort.
        """
        if time.time() < self.circuit_breaker_until:
            wait_time = self.circuit_breaker_until - time.time()
            raise RuntimeError(
                f"Circuit breaker active. Skipping calls for {wait_time:.1f}s"
            )

        model_name = self.cfg.pro_model if model_type == "pro" else self.cfg.flash_model
        litellm_model = (
            f"gemini/{model_name}"
            if not model_name.startswith("gemini/")
            else model_name
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        kwargs = {}
        # Gemini 2.5 Series
        if re.search(r"2\.5", model_name):
            if "flash" in model_name:
                kwargs["extra_body"] = {
                    "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}}
                }
        # Gemini 3.0/3.1 Series
        elif re.search(r"(?<!\d)3(?:\.\d+)?(?!\d)", model_name):
            if "flash" in model_name:
                kwargs["extra_body"] = {
                    "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}
                }
            elif "pro" in model_name:
                kwargs["extra_body"] = {
                    "generationConfig": {"thinkingConfig": {"thinkingLevel": "high"}}
                }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        kwargs["timeout"] = 45  # Enforce a 45s hard timeout to prevent indefinite hangs

        last_error: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                start = time.time()
                response = litellm.completion(
                    model=litellm_model,
                    messages=messages,
                    **kwargs,
                )
                self._log(
                    f"[{litellm_model}] Response time: {time.time() - start:.1f}s"
                )
                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise ValueError("LLM returned empty content")
                self.consecutive_failures = 0
                return content.strip()
            except Exception as e:
                last_error = e
                self.consecutive_failures += 1
                self._log(
                    f"[{litellm_model}] Attempt {attempt}/{self.MAX_RETRIES} failed: {e}"
                )

                if self.consecutive_failures >= 3:
                    self.circuit_breaker_until = (
                        time.time() + self.CIRCUIT_BREAKER_COOLDOWN
                    )
                    self._log(
                        f"[{litellm_model}] Circuit breaker tripped. Cooling down for {self.CIRCUIT_BREAKER_COOLDOWN}s"
                    )
                    break

                if attempt < self.MAX_RETRIES:
                    time.sleep(min(2**attempt, 4))  # Cap backoff at 4 seconds

        raise RuntimeError(
            f"LLM call failed after consecutive attempts. Last error: {last_error}"
        )
