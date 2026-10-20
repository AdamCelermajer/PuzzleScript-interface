"""OpenCode harness: ``opencode run --format json``, resumed with ``--session <id>``.

Config is private (``OPENCODE_CONFIG`` plus throwaway XDG dirs), never the user's
``~/.config/opencode``. The system prompt is an ``instructions`` file; models
unknown to models.dev are declared under ``provider.<p>.models``.

OpenCode only forwards an attached image when the model's config declares image input;
otherwise it replaces the image with "ERROR: Cannot read ... (this model does not support
image input)". Image input is therefore declared from the provider's own model list.
"""
from __future__ import annotations

import functools
import json
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from harnesses.base import CliSession, add_usage, usage_record

WEB_TOOLS = ("webfetch", "websearch", "codesearch")
FILE_TOOLS = {"edit", "write", "patch", "multiedit"}
# OpenRouter's reasoning ceiling is xhigh (as in the bare harness).
VARIANT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}
NANOGPT_BASE_URL = "https://nano-gpt.com/api/v1"
MODEL_LISTS = {"openrouter": "https://openrouter.ai/api/v1/models",
               "nanogpt": f"{NANOGPT_BASE_URL}/models?detailed=true"}


@functools.lru_cache(maxsize=None)
def _model_list(provider: str) -> dict[str, dict]:
    with urllib.request.urlopen(MODEL_LISTS[provider], timeout=20) as response:
        return {str(m.get("id")): m for m in json.load(response).get("data", []) if isinstance(m, dict)}


def image_input(provider: str, native_model: str) -> bool | None:
    """Whether the provider lists image input for the model; None when the list is unavailable."""
    try:
        entry = _model_list(provider).get(native_model) if provider in MODEL_LISTS else None
    except (OSError, ValueError):
        return None
    if entry is None:
        return None
    if provider == "nanogpt":
        return bool((entry.get("capabilities") or {}).get("vision"))
    return "image" in ((entry.get("architecture") or {}).get("input_modalities") or [])


def opencode_config(provider: str, native_model: str, instructions: Path, pin_provider: str = "",
                    images: bool = True) -> dict[str, Any]:
    model: dict[str, Any] = {}
    if images:
        model.update({"attachment": True, "modalities": {"input": ["text", "image"], "output": ["text"]}})
    if pin_provider:
        model["options"] = {"provider": {"order": [pin_provider], "allow_fallbacks": False}}
    provider_entry: dict[str, Any] = {"models": {native_model: model}}
    if provider == "nanogpt":
        provider_entry.update({"npm": "@ai-sdk/openai-compatible", "name": "NanoGPT",
                               "options": {"baseURL": NANOGPT_BASE_URL, "apiKey": "{env:NANOGPT_API_KEY}"}})
    return {
        "$schema": "https://opencode.ai/config.json",
        "autoupdate": False,
        "share": "disabled",
        "instructions": [str(instructions)],
        "permission": {"*": "allow", **{tool: "deny" for tool in WEB_TOOLS}},
        "provider": {provider: provider_entry},
    }


class OpenCodeSession(CliSession):
    harness_id = "opencode"

    def prepare(self) -> None:
        self.binary = shutil.which("opencode") or "opencode"
        instructions = self.private / "SYSTEM_PROMPT.md"
        instructions.write_text(self.system_prompt, encoding="utf-8")
        config = self.private / "opencode.json"
        listed = image_input(self.provider, self.native_model)
        # An unlisted model is assumed to take images: a refused image fails loudly,
        # a stripped one would silently leave the agent without the frame.
        self.manifest_extra = {"image_input": listed is not False,
                               "image_input_source": "provider model list" if listed is not None else "assumed (model not listed)"}
        config.write_text(json.dumps(opencode_config(self.provider, self.native_model, instructions,
                                                     self.pin_provider, images=listed is not False), indent=2), encoding="utf-8")
        self.env["OPENCODE_CONFIG"] = str(config)
        self.env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
        # Never read or write a real OpenCode install (T3 Code depends on the host one).
        for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            path = self.private / name.lower()
            path.mkdir(exist_ok=True)
            self.env[name] = str(path)

    def command(self, instruction: str, images: Sequence[Path]) -> list[str]:
        command = [self.binary, "run", instruction, "--format", "json", "--thinking",
                   "--dangerously-skip-permissions", "-m", f"{self.provider}/{self.native_model}",
                   "--variant", VARIANT[self.effort]]
        if self.session_id:
            command += ["--session", self.session_id]
        for image in images:
            command += ["-f", str(image)]
        return command

    def normalize(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        if event.get("sessionID"):
            self.session_id = str(event["sessionID"])
        kind = event.get("type")
        part = event.get("part") or {}
        if kind == "text":
            text = str(part.get("text") or "")
            self._text_parts.append(text)
            return [{"type": "message", "text": text}]
        if kind == "reasoning":
            return [{"type": "reasoning", "text": str(part.get("text") or "")}]
        if kind == "tool_use":
            # The answer is the text after the last tool call.
            self._text_parts = []
            return [self._tool_event(part)]
        if kind == "step_finish":
            tokens = part.get("tokens") or {}
            cache = tokens.get("cache") or {}
            step = usage_record(tokens.get("input"), tokens.get("output"), tokens.get("reasoning"), cache.get("read"))
            if isinstance(part.get("cost"), (int, float)):
                step["cost_usd"] = part["cost"]
            add_usage(self._usage, step)
            return []
        if kind == "error":
            error = event.get("error") or {}
            message = str((error.get("data") or {}).get("message") or error.get("name") or error or "error")
            self._turn_errors.append(message)
            return [{"type": "error", "text": message}]
        return []

    @staticmethod
    def _tool_event(part: dict[str, Any]) -> dict[str, Any]:
        name = str(part.get("tool") or "tool")
        state = part.get("state") or {}
        arguments = state.get("input") or {}
        output = state.get("output") if state.get("output") is not None else state.get("error")
        metadata = state.get("metadata") or {}
        if name == "bash":
            return {"type": "command", "text": str(arguments.get("command") or ""), "output": str(output or ""),
                    "exit_code": metadata.get("exit")}
        if name in FILE_TOOLS:
            return {"type": "file_change", "tool": name, "text": str(arguments.get("filePath") or ""),
                    "output": str(output or "")}
        return {"type": "tool", "tool": name, "text": arguments, "output": str(output or "")}
