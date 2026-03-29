import os
import time
from dataclasses import dataclass, field
from typing import Optional

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

    def __init__(self, config: Config) -> None:
        """Initialize provider credentials and runtime config."""
        self.cfg = config
        os.environ["GEMINI_API_KEY"] = config.api_key

    def _call(self, system: str, prompt: str, model_type: str = "flash") -> str:
        """Call the configured LLM and return plain text output."""
        litellm_model = None
        try:
            start = time.time()
            model_name = self.cfg.pro_model if model_type == "pro" else self.cfg.flash_model
            litellm_model = f"gemini/{model_name}" if not model_name.startswith("gemini/") else model_name

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]

            kwargs = {}

            # Gemini 2.5 Series (Uses thinking_budget)
            if "2.5" in model_name:
                if "flash" in model_name:
                    # 0 budget disables the reasoning loop entirely for sub-second responses
                    kwargs["extra_body"] = {"generationConfig": {"thinkingConfig": {"thinkingBudget": 0}}}

            # Gemini 3.0 Series (Uses thinking_level)
            elif "3" in model_name:
                if "flash" in model_name:
                    kwargs["extra_body"] = {"generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
                elif "pro" in model_name:
                    kwargs["extra_body"] = {"generationConfig": {"thinkingConfig": {"thinkingLevel": "high"}}}

            response = litellm.completion(
                model=litellm_model,
                messages=messages,
                **kwargs,
            )
            print(f"[{litellm_model}] Response time: {time.time() - start:.1f}s")
            content = response.choices[0].message.content
            return content.strip() if content else "wait"
        except Exception as e:
            print(f"Error calling {litellm_model or 'model'}: {e}")
            return "wait"
