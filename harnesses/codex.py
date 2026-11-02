"""Codex CLI harness: ``codex exec --json`` resumed with ``codex exec resume <thread_id>``."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from harnesses.base import CliSession, usage_record

# Web search, browser/computer use, plugins, connectors and memories are off.
DISABLED_CONFIG = (
    'web_search="disabled"',
    "project_doc_max_bytes=0",
    "features.browser_use=false",
    "features.computer_use=false",
    "features.apps=false",
    "features.plugins=false",
    "features.image_generation=false",
    "features.memories=false",
    "features.multi_agent=false",
    "memories.use_memories=false",
    "memories.generate_memories=false",
)
# Transport only, so the recorder can read every call: the ChatGPT-login provider declared again with the
# recorder as its base URL, over plain HTTP (no WebSocket) and with request bodies not zstd-compressed.
RECORDABLE_CONFIG = ('model_provider="recorded"', 'model_providers.recorded.name="OpenAI (recorded)"',
                     'model_providers.recorded.wire_api="responses"', "model_providers.recorded.requires_openai_auth=true",
                     "model_providers.recorded.supports_websockets=false", "features.enable_request_compression=false")


CHATGPT_CODEX_API = "https://chatgpt.com/backend-api/codex"


def find_codex_bin(explicit: str = "") -> str | None:
    """Locate a Codex executable (explicit, $CODEX_BIN, Windows app install, PATH)."""
    requested = explicit.strip() or os.getenv("CODEX_BIN", "").strip()
    if requested:
        return requested
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "")
        if local_app_data:
            candidates = sorted((Path(local_app_data) / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"),
                                key=lambda path: path.stat().st_mtime, reverse=True)
            if candidates:
                return str(candidates[0])
    return shutil.which("codex")


def codex_oauth_status(explicit_bin: str = "") -> dict[str, object]:
    """Host-side Codex login status (used by the historical workbench page)."""
    codex_bin = find_codex_bin(explicit_bin)
    if not codex_bin:
        return {"available": False, "logged_in": False, "state": "runtime_missing",
                "message": "Codex runtime was not found.", "version": ""}
    try:
        version = subprocess.run([codex_bin, "--version"], capture_output=True, text=True, timeout=10, check=False)
        login = subprocess.run([codex_bin, "login", "status"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "logged_in": False, "state": "unavailable", "message": str(exc), "version": ""}
    login_text = " ".join((login.stdout or login.stderr or "").split())
    logged_in = login.returncode == 0 and "logged in" in login_text.lower()
    return {"available": version.returncode == 0, "logged_in": logged_in,
            "state": "ready" if logged_in else "login_required",
            "message": login_text or "Codex login status unavailable.",
            "version": " ".join((version.stdout or version.stderr or "").split())}


class CodexSession(CliSession):
    harness_id = "codex"

    def prepare(self) -> None:
        self.binary = find_codex_bin() or "codex"
        # With a ChatGPT login Codex calls this endpoint (OPENAI_BASE_URL does not replace it).
        self.api_base = self.record_calls(CHATGPT_CODEX_API)

    def command(self, instruction: str, images: Sequence[Path]) -> list[str]:
        command = [self.binary, "exec", "--json", "--skip-git-repo-check",
                   "--dangerously-bypass-approvals-and-sandbox", "-m", self.native_model,
                   "-c", f"model_reasoning_effort={json.dumps(self.effort)}",
                   # The same system prompt text, re-sent on every resumed process.
                   "-c", f"developer_instructions={json.dumps(self.system_prompt)}",
                   "-c", f"model_providers.recorded.base_url={json.dumps(self.api_base)}"]
        for item in DISABLED_CONFIG + RECORDABLE_CONFIG:
            command += ["-c", item]
        if self.session_id:
            command.append("resume")
        for image in images:
            command += ["-i", str(image)]
        # `--` keeps a variadic -i from swallowing the positionals.
        command.append("--")
        if self.session_id:
            command.append(self.session_id)
        command.append(instruction)
        return command

    def step_finished(self, event: dict[str, Any]) -> bool:
        return event.get("type") == "item.completed" and (event.get("item") or {}).get("type") == "command_execution"

    def normalize(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        kind = event.get("type")
        if kind == "thread.started":
            self.session_id = str(event.get("thread_id") or self.session_id)
            return []
        if kind == "turn.completed":
            usage = event.get("usage") or {}
            self._usage = usage_record(usage.get("input_tokens"), usage.get("output_tokens"),
                                       usage.get("reasoning_output_tokens"), usage.get("cached_input_tokens"))
            return []
        if kind == "turn.failed":
            message = str((event.get("error") or {}).get("message") or "turn failed")
            self._turn_errors.append(message)
            return [{"type": "error", "text": message}]
        if kind == "error":
            message = str(event.get("message") or "error")
            self._turn_errors.append(message)
            return [{"type": "error", "text": message}]
        if kind != "item.completed":
            return []
        item = event.get("item") or {}
        item_type = item.get("type")
        if item_type == "agent_message":
            text = str(item.get("text") or "")
            self._final_text = text  # the turn's answer is the last agent message
            return [{"type": "message", "text": text}]
        if item_type == "reasoning":
            return [{"type": "reasoning", "text": str(item.get("text") or "")}]
        if item_type == "command_execution":
            return [{"type": "command", "text": str(item.get("command") or ""),
                     "output": str(item.get("aggregated_output") or ""), "exit_code": item.get("exit_code")}]
        if item_type == "file_change":
            changes = item.get("changes") or []
            text = ", ".join(f"{change.get('kind', 'update')} {change.get('path', '')}" for change in changes)
            return [{"type": "file_change", "text": text}]
        if item_type == "mcp_tool_call":
            return [{"type": "tool", "tool": f"{item.get('server', '')}/{item.get('tool', '')}",
                     "text": item.get("arguments"), "output": item.get("result") or item.get("error")}]
        if item_type == "web_search":
            return [{"type": "tool", "tool": "web_search", "text": str(item.get("query") or "")}]
        if item_type == "error":
            return [{"type": "error", "text": str(item.get("message") or "")}]
        return [{"type": "tool", "tool": str(item_type), "text": item}]
