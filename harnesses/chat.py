"""Plain chat-completions transport (OpenRouter or NanoGPT) for the ``bare`` harness.

Retry policy, request recording and the context-window policy live here; the
tool-calling loop lives in ``harnesses/bare.py``.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from harnesses.model_provider import API_PROVIDERS, api_key

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter's unified reasoning parameter has no "max"; xhigh is its ceiling.
EFFORT_SENT = {"none": "none", "minimal": "minimal", "low": "low", "medium": "medium",
               "high": "high", "xhigh": "xhigh", "max": "xhigh"}
TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}
DEFAULT_CONTEXT_CHARS = int(os.environ.get("HARNESS_CONTEXT_CHARS", "240000"))


class ProviderError(RuntimeError):
    """Non-retryable provider failure (auth, credits, invalid request)."""


def provider_routing(provider: str) -> dict[str, Any] | None:
    """Pin one OpenRouter provider (no fallback) so quantization stays fixed."""
    return {"order": [provider], "allow_fallbacks": False} if provider else None


def openrouter_key() -> str:
    key_file = os.environ.get("AVO_OPENROUTER_KEY_FILE", "")
    if key_file:
        key = Path(key_file).read_text(encoding="utf-8").strip()
    else:
        key = ""
        env_file = Path(__file__).resolve().parents[1] / ".env"
        if env_file.is_file():
            from dotenv import dotenv_values
            key = str(dotenv_values(env_file).get("OPENROUTER_API_KEY") or "").strip()
        key = key or os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ProviderError("OpenRouter requires OPENROUTER_API_KEY or AVO_OPENROUTER_KEY_FILE")
    return key


def image_part(path: str | Path) -> dict[str, Any]:
    """History placeholder; only the newest image is materialized when sending."""
    return {"type": "image_path", "path": str(Path(path).resolve())}


class OpenRouterChat:
    def __init__(self, model: str, effort: str, request_dir: str | Path, *,
                 context_chars: int = DEFAULT_CONTEXT_CHARS, max_attempts: int = 8, provider: str = "",
                 request_timeout: float = 900.0, model_provider: str = "openrouter") -> None:
        details = API_PROVIDERS[model_provider]
        self.model_provider = model_provider
        self.label = details["label"]
        self.api_url = details["origin"] + "/api/v1/chat/completions"
        if model_provider != "openrouter" and provider:
            raise ValueError("Provider pinning is only supported for OpenRouter")
        if effort not in EFFORT_SENT:
            raise ValueError(f"Unsupported reasoning effort: {effort}")
        self.model = model
        self.effort = effort
        self.effort_sent = EFFORT_SENT[effort] if model_provider == "openrouter" else effort
        self.provider = provider
        self.request_dir = Path(request_dir)
        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.context_chars = context_chars
        self.max_attempts = max_attempts
        self.request_timeout = request_timeout
        if model_provider == "openrouter":
            self._key = openrouter_key()
        else:
            try:
                self._key = api_key(model_provider, env_file=Path(__file__).resolve().parents[1] / ".env")
            except RuntimeError as exc:
                raise ProviderError(str(exc)) from None
        self._sequence = 0
        self.usage_totals: dict[str, float] = {}
        self.elided_messages = 0

    def complete(self, messages: list[dict[str, Any]], tools: list[dict] | None = None,
                 tool_choice: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (assistant_message, call_record). Retries transient failures."""
        view = self._view(messages)
        body: dict[str, Any] = {"model": self.model, "messages": view,
                                "reasoning": {"effort": self.effort_sent}}
        if self.model_provider == "openrouter":
            body["usage"] = {"include": True}
        if self.provider:
            body["provider"] = provider_routing(self.provider)
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        payload = json.dumps(body).encode("utf-8")
        self._sequence += 1
        started = time.time()
        attempts: list[str] = []
        response: dict[str, Any] | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._post(payload)
                choices = response.get("choices") or []
                if response.get("error") or not choices or not isinstance(choices[0].get("message"), dict):
                    raise _Transient(f"provider returned no message: {json.dumps(response.get('error') or response)[:500]}")
                break
            except _Transient as exc:
                attempts.append(str(exc))
                if attempt == self.max_attempts:
                    self._record(body, None, attempts, started)
                    raise RuntimeError(f"{self.label} failed after {attempt} attempts: {exc}") from None
                time.sleep(min(60.0, 2.0 ** attempt))
            except ProviderError as exc:
                attempts.append(str(exc))
                self._record(body, None, attempts, started)
                raise
        assert response is not None
        message = response["choices"][0]["message"]
        assistant: dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            assistant["tool_calls"] = message["tool_calls"]
        if message.get("reasoning_details"):
            # Returned unchanged so reasoning models keep continuity across tool calls.
            assistant["reasoning_details"] = message["reasoning_details"]
        for key, value in (response.get("usage") or {}).items():
            if isinstance(value, (int, float)):
                self.usage_totals[key] = self.usage_totals.get(key, 0) + value
        record = self._record(body, response, attempts, started)
        record["reasoning"] = message.get("reasoning") or ""
        return assistant, record

    def _post(self, payload: bytes) -> dict[str, Any]:
        request = urllib.request.Request(self.api_url, data=payload, method="POST", headers={
            "Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
            "X-Title": "PuzzleScript harness ladder"})
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as stream:
                return json.loads(stream.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if exc.code in TRANSIENT_STATUS:
                raise _Transient(f"HTTP {exc.code}: {detail}") from None
            raise ProviderError(f"{self.label} HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise _Transient(f"{type(exc).__name__}: {exc}") from None
        except json.JSONDecodeError as exc:
            raise _Transient(f"invalid JSON response: {exc}") from None

    def _view(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Materialize the newest image, then drop the oldest exchanges over budget.

        Messages 0 (system) and 1 (first instruction) are always kept. Removal happens
        in whole groups: a user message, or an assistant message with the tool results
        answering it, so tool calls are never separated from their results.
        """
        latest_image = None
        for index, message in enumerate(messages):
            if isinstance(message.get("content"), list) and any(
                    part.get("type") == "image_path" for part in message["content"]):
                latest_image = index
        view = []
        for index, message in enumerate(messages):
            content = message.get("content")
            if isinstance(content, list):
                parts = []
                for part in content:
                    if part.get("type") != "image_path":
                        parts.append(part)
                    elif index == latest_image:
                        data = base64.b64encode(Path(part["path"]).read_bytes()).decode("ascii")
                        parts.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + data}})
                    else:
                        parts.append({"type": "text", "text": "[earlier frame image omitted]"})
                message = {**message, "content": parts}
            view.append(message)
        head, groups = view[:2], []
        for message in view[2:]:
            if message.get("role") in {"user", "assistant"} or not groups:
                groups.append([])
            groups[-1].append(message)
        size = lambda items: sum(_chars(item) for item in items)
        dropped = 0
        while len(groups) > 1 and size(head) + sum(size(group) for group in groups) > self.context_chars:
            dropped += len(groups.pop(0))
        self.elided_messages = dropped
        if dropped:
            head = head + [{"role": "user", "content": (
                f"[{dropped} earlier messages were removed to fit the context budget. "
                "Rely on your saved notes, files and the current state.]")}]
        return head + [message for group in groups for message in group]

    def _record(self, body: dict, response: dict | None, attempts: list[str], started: float) -> dict[str, Any]:
        record = {
            "sequence": self._sequence, "model": self.model, "model_provider": self.model_provider,
            "effort_requested": self.effort,
            "effort_sent": self.effort_sent, "duration_s": round(time.time() - started, 3),
            "retries": attempts, "elided_messages": self.elided_messages,
            "usage": (response or {}).get("usage"), "provider": (response or {}).get("provider"),
        }
        stored = {**body, "messages": [_without_image_data(message) for message in body["messages"]]}
        path = self.request_dir / f"request-{time.time_ns()}-{self._sequence:06d}.json"
        path.write_text(json.dumps({**record, "request": stored, "response": response}, indent=1),
                        encoding="utf-8")
        return record


class _Transient(Exception):
    pass


def _chars(message: dict[str, Any]) -> int:
    content = message.get("content")
    if isinstance(content, list):
        total = sum(len(part.get("text", "")) for part in content) + 1000 * sum(
            1 for part in content if part.get("type") == "image_url")
    else:
        total = len(str(content or ""))
    return (total + len(json.dumps(message.get("tool_calls") or ""))
            + len(json.dumps(message.get("reasoning_details") or "")))


def _without_image_data(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if not isinstance(content, list):
        return message
    parts = []
    for part in content:
        if part.get("type") == "image_url":
            url = part["image_url"]["url"]
            parts.append({"type": "image_url", "image_url": {
                "url": "[png sha256=" + hashlib.sha256(url.encode("ascii")).hexdigest()[:16] + "]"}})
        else:
            parts.append(part)
    return {**message, "content": parts}
