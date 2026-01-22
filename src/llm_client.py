import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from google import genai

load_dotenv()

@dataclass
class Config:
    server_url: str = "http://localhost:3000"
    model: str = "gemini-2.0-flash-lite-preview-02-05"
    game: str = "sokoban-basic"
    mode: str = "learn"
    max_steps: int = 50
    show_legend: bool = False
    api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    rules_dir: str = "rules"

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found")


class Server:
    def __init__(self, url: str):
        self.url = url

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        try:
            r = requests.post(f"{self.url}/{endpoint}", json=data, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"Error: {e}")
            return None

    def init(self, game: str) -> Optional[dict]:
        return self._post("init", {"gameName": game})

    def action(self, session: str, action: str) -> Optional[dict]:
        return self._post("action", {"sessionId": session, "action": action})


class LlmClient:
    def __init__(self, config: Config):
        self.cfg = config
        self.llm = genai.Client(api_key=config.api_key)

    def _call(self, system: str, prompt: str) -> str:
        try:
            t = time.time()
            r = self.llm.models.generate_content(
                model=self.cfg.model,
                contents=f"{system}\n\n{prompt}"
            )
            print(f"Response time: {time.time()-t:.1f}s")
            return r.text.strip() if r.text else "wait"
        except Exception as e:
            print(f"Error: {e}")
            return "wait"
