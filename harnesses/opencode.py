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
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from harnesses.base import CliSession, HarnessError, add_usage, usage_record
from harnesses.model_provider import VAST_BASE_URL

WEB_TOOLS = ("webfetch", "websearch", "codesearch")
FILE_TOOLS = {"edit", "write", "patch", "multiedit"}
# OpenRouter's reasoning ceiling is xhigh (as in the bare harness).
VARIANT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}
NANOGPT_BASE_URL = "https://nano-gpt.com/api/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OUTPUT_TOKEN_MAX = 64_000
# @opencode-ai/plugin, which custom tools import, installed in the agents image (harnesses/docker/Dockerfile).
PLUGIN_DIR = Path("/opt/opencode-plugin")
MODEL_LISTS = {"openrouter": "https://openrouter.ai/api/v1/models",
               "nanogpt": f"{NANOGPT_BASE_URL}/models?detailed=true"}
# Context limits models.dev gets wrong for a host we pin. models.dev lists 1M tokens for qwen3.8-27b
# (from the Alibaba/Novita/Phala endpoints), so OpenCode would never compact, and a 262k host
# rejects the request first. Declaring the real limit makes OpenCode compact near 198k instead.
KNOWN_CONTEXT = {("openrouter", "qwen/qwen3.8-27b"): 262_144}
# Qwen3.8's maximum thinking, asked for in every vast.ai request (the server defaults to the same).
# OpenCode sends no effort for this provider, so --effort does not change it.
VAST_THINKING = {"enable_thinking": True, "reasoning_effort": "xhigh"}
# OpenCode forces temperature 0.55 and top_p 1 on any id containing "qwen" and sends no top_k (the vast
# served name has no "qwen", so vLLM used the model's own). Qwen's thinking-mode settings (model card,
# generation_config.json) replace them; top_k goes in the request body with the model options.
QWEN_SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
# OpenCode sends no effort for "qwen" ids either (--variant is a no-op), so OpenRouter gets it in the body.


def vast_model(native_model: str) -> dict[str, Any]:
    """The self-hosted endpoint and the weights behind the served name (vLLM ``/v1/models``)."""
    endpoint = (os.environ.get("VAST_LLM_BASE_URL") or VAST_BASE_URL).rstrip("/")
    try:
        with urllib.request.urlopen(f"{endpoint}/models", timeout=20) as response:
            served = {str(m.get("id")): m for m in json.load(response).get("data", []) if isinstance(m, dict)}
    except (OSError, ValueError) as exc:
        raise HarnessError(f"The vast.ai endpoint {endpoint} is unreachable ({exc}); is the SSH tunnel up?") from None
    if native_model not in served:
        raise HarnessError(f"{endpoint} serves {', '.join(served) or 'no model'}, not {native_model}")
    # OpenCode forces temperature 0.55 / top_p 1 for ids containing "qwen" and sends none otherwise;
    # vLLM's defaults are the model's generation_config.json.
    sampling = ("temperature 0.55, top_p 1 (OpenCode for qwen ids), top_k 20 (server)" if "qwen" in native_model.lower()
                else "temperature 1.0, top_p 0.95, top_k 20 (server default, generation_config.json)")
    # Declared limits make OpenCode compact near the context end instead of overflowing it.
    limit = {"context": served[native_model].get("max_model_len"), "output": OUTPUT_TOKEN_MAX}
    return {"endpoint": endpoint, "served_model": native_model, "served_weights": served[native_model].get("root"),
            "opencode_limit": limit, "thinking": VAST_THINKING, "sampling": sampling}


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
                    images: bool = True, served: dict[str, Any] | None = None, effort: str = "",
                    base_url: str = "") -> dict[str, Any]:
    model: dict[str, Any] = {}
    options: dict[str, Any] = {}
    if images:
        model.update({"attachment": True, "modalities": {"input": ["text", "image"], "output": ["text"]}})
    if pin_provider:
        # NanoGPT rejects an unknown id in provider.only (its X-Provider header silently falls back).
        pin = {"only": [pin_provider]} if provider == "nanogpt" else {"order": [pin_provider]}
        options["provider"] = {**pin, "allow_fallbacks": False}
    qwen = "qwen" in native_model.lower() and provider != "vast"
    if qwen:
        options["top_k"] = QWEN_SAMPLING["top_k"]
        model["temperature"] = True  # OpenCode sends a temperature only for models declared to take one
    if qwen and provider == "openrouter" and effort:
        options["reasoning"] = {"effort": VARIANT[effort]}
    if options:
        model["options"] = options
    if (provider, native_model) in KNOWN_CONTEXT:
        model["limit"] = {"context": KNOWN_CONTEXT[provider, native_model], "output": OUTPUT_TOKEN_MAX}
    provider_entry: dict[str, Any] = {"models": {native_model: model}}
    if provider == "nanogpt":
        provider_entry.update({"npm": "@ai-sdk/openai-compatible", "name": "NanoGPT",
                               "options": {"baseURL": NANOGPT_BASE_URL, "apiKey": "{env:NANOGPT_API_KEY}"}})
    if provider == "vast" and served:
        # Without a limit OpenCode never compacts, and vLLM rejects prompt + max_tokens > context.
        model.update({"options": {"chat_template_kwargs": served["thinking"]}, "limit": served["opencode_limit"]})
        provider_entry.update({"npm": "@ai-sdk/openai-compatible", "name": "vast.ai vLLM",
                               "options": {"baseURL": served["endpoint"], "apiKey": "unused"}})
    if base_url:
        # The call recorder: every request goes through it to the real endpoint.
        provider_entry.setdefault("options", {})["baseURL"] = base_url
    config = {
        "$schema": "https://opencode.ai/config.json",
        "autoupdate": False,
        "share": "disabled",
        "instructions": [str(instructions)],
        "permission": {"*": "allow", **{tool: "deny" for tool in WEB_TOOLS}},
        "provider": {provider: provider_entry},
        # Each new session would otherwise ask a small model (Claude Haiku on OpenRouter) for a title.
        "agent": {"title": {"disable": True}},
    }
    if qwen:
        # An agent's own temperature/top_p override OpenCode's per-model defaults; `run` uses build,
        # the task tool general/explore.
        sampling = {"temperature": QWEN_SAMPLING["temperature"], "top_p": QWEN_SAMPLING["top_p"]}
        config["agent"].update({name: dict(sampling) for name in ("build", "plan", "general", "explore")})
    return config


def tool_source(tool: dict[str, Any], workspace: Path) -> str:
    """An OpenCode custom tool (opencode/tools/<name>.ts) that runs ``tool["command"]`` in the workspace."""
    if tool.get("argument"):
        args = f'{{ {tool["argument"]}: tool.schema.string().describe({json.dumps(tool["argument_description"])}) }}'
        command = " ".join(tool["command"]) + f' ${{args.{tool["argument"]}}}'
    else:
        args, command = "{}", " ".join(tool["command"])
    return f'''import {{ tool }} from "@opencode-ai/plugin"

export default tool({{
  description: {json.dumps(tool["description"])},
  args: {args},
  async execute(args) {{
    const result = await Bun.$`{command}`.cwd({json.dumps(str(workspace))}).nothrow().quiet()
    return (result.stdout.toString() + result.stderr.toString()).trim()
  }},
}})
'''


class OpenCodeSession(CliSession):
    harness_id = "opencode"
    native_tools = True

    def prepare(self) -> None:
        self.binary = shutil.which("opencode") or "opencode"
        instructions = self.private / "SYSTEM_PROMPT.md"
        instructions.write_text(self.system_prompt, encoding="utf-8")
        config = self.private / "opencode.json"
        served = vast_model(self.native_model) if self.provider == "vast" else None
        listed = True if served else image_input(self.provider, self.native_model)
        base_url = self.record_calls(served["endpoint"] if served else {"openrouter": OPENROUTER_BASE_URL,
                                                                        "nanogpt": NANOGPT_BASE_URL}[self.provider])
        # An unlisted model is assumed to take images: a refused image fails loudly,
        # a stripped one would silently leave the agent without the frame.
        self.manifest_extra = {"image_input": listed is not False,
                               "image_input_source": "self-hosted model (images checked at setup)" if served
                               else "provider model list" if listed is not None else "assumed (model not listed)",
                               **(served or {})}
        config.write_text(json.dumps(opencode_config(self.provider, self.native_model, instructions, self.pin_provider,
                                                     images=listed is not False, served=served, effort=self.effort,
                                                     base_url=base_url),
                                     indent=2), encoding="utf-8")
        if "qwen" in self.native_model.lower() and self.provider != "vast":
            self.manifest_extra["sampling"] = "temperature 1.0, top_p 0.95, top_k 20 (Qwen thinking mode, set by us)"
            if self.provider == "openrouter":
                self.manifest_extra["effort_sent"] = VARIANT[self.effort]
        self.env["OPENCODE_CONFIG"] = str(config)
        self.env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
        # OpenCode caps one reply at 32k output tokens; a thinking model can spend all of it reasoning
        # and return nothing. Harness² upstream runs every OpenCode session with 64k.
        self.env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(OUTPUT_TOKEN_MAX)
        self.manifest_extra["output_token_max"] = OUTPUT_TOKEN_MAX
        if (self.provider, self.native_model) in KNOWN_CONTEXT:
            self.manifest_extra["opencode_limit"] = {"context": KNOWN_CONTEXT[self.provider, self.native_model],
                                                     "output": OUTPUT_TOKEN_MAX}
        # Never read or write a real OpenCode install (T3 Code depends on the host one).
        for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            path = self.private / name.lower()
            path.mkdir(exist_ok=True)
            self.env[name] = str(path)
        # The caller's tools, next to OpenCode's own: global custom tools in the private config,
        # out of the agent's folder.
        tools = self.private / "xdg_config_home" / "opencode" / "tools"
        for tool in self.game_tools:
            tools.mkdir(parents=True, exist_ok=True)
            (tools / f"{tool['name']}.ts").write_text(tool_source(tool, self.workspace), encoding="utf-8")
        if self.game_tools and PLUGIN_DIR.is_dir():
            for name in ("package.json", "package-lock.json"):
                shutil.copyfile(PLUGIN_DIR / name, tools.parent / name)
            shutil.copytree(PLUGIN_DIR / "node_modules", tools.parent / "node_modules", symlinks=True)

    def command(self, instruction: str, images: Sequence[Path]) -> list[str]:
        command = [self.binary, "run", instruction, "--format", "json", "--thinking",
                   "--dangerously-skip-permissions", "-m", f"{self.provider}/{self.native_model}",
                   "--variant", VARIANT[self.effort]]
        if self.session_id:
            command += ["--session", self.session_id]
        for image in images:
            command += ["-f", str(image)]
        return command

    def step_finished(self, event: dict[str, Any]) -> bool:
        # OpenCode has saved the whole step, tool results included.
        return event.get("type") == "step_finish"

    def normalize(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        if event.get("sessionID"):
            self.session_id = str(event["sessionID"])
        kind = event.get("type")
        part = event.get("part") or {}
        if kind == "text":
            if part.get("synthetic"):
                # After a compaction OpenCode streams the summary, then this synthetic "Continue ..."
                # prompt, then the answer: drop the summary and the prompt from the final text.
                self._text_parts = []
                return []
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
