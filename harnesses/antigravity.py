"""Antigravity CLI harness: ``agy -p --output-format stream-json``, resumed with ``--conversation``.

Credentials live in the Docker volume mounted at ``~/.gemini`` (filled once by
``python -m harnesses.launch login antigravity``). ``agy`` has no system-prompt or
image flag: the system prompt prefixes the first turn and images are referenced by
workspace path. Web/browser tools are blocked by a global ``PreToolUse`` hook in
``~/.gemini/config/hooks.json`` that returns ``{"decision": "deny"}``.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Sequence

from harnesses.base import CliSession, usage_record

WEB_TOOL_MATCHER = ("search_web|web_search|read_url_content|view_content_chunk|execute_url|open_browser_url|"
                    "browser_.*|mcp_chrome.*|chrome_devtools.*")
DENY_HOOK = {
    "puzzlescript-no-web": {
        "PreToolUse": [{
            "matcher": WEB_TOOL_MATCHER,
            "hooks": [{"type": "command", "timeout": 10, "command": (
                "cat >/dev/null; echo '{\"decision\":\"deny\",\"reason\":\"Web search, URL reading and "
                "browser tools are disabled in this experiment.\"}'")}],
        }],
    },
}
# The CLI may keep its token store under ~/.config/antigravity; the image links that
# directory into the ~/.gemini volume so a login persists.
XDG_LINK_TARGET = "xdg-antigravity"


def gemini_home() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))) / ".gemini"


def install_web_deny_hook(home: Path | None = None) -> Path:
    root = (home or gemini_home())
    (root / XDG_LINK_TARGET).mkdir(parents=True, exist_ok=True)
    path = root / "config" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged = {**existing, **DENY_HOOK}
    if merged != existing:
        temporary = path.with_name(f".hooks.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        temporary.replace(path)
    return path


class AntigravitySession(CliSession):
    harness_id = "antigravity"

    def prepare(self) -> None:
        self.binary = shutil.which("agy") or "agy"
        self.unrecorded = "agy calls Google's service itself and has no API base-URL setting"
        install_web_deny_hook()
        self._tools_seen: dict[str, str] = {}

    def _prompt(self, instruction: str, images: Sequence[Path]) -> str:
        text = instruction
        if not self.session_id and self.turn_number <= 1:
            text = f"{self.system_prompt}\n\n---\n\n{instruction}"
        for image in images:
            try:
                shown = image.relative_to(self.workspace).as_posix()
            except ValueError:
                shown = str(image)
            text += f"\n\n[Image attached as file: {shown} - open it with your file viewing tool.]"
        return text

    def command(self, instruction: str, images: Sequence[Path]) -> list[str]:
        command = [self.binary, "-p", self._prompt(instruction, images), "--output-format", "stream-json",
                   "--dangerously-skip-permissions", "--disable-slash-commands",
                   "--model", self.native_model, "--effort", self.effort]
        if self.session_id:
            command += ["--conversation", self.session_id]
        return command

    def normalize(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        kind = str(event.get("event") or event.get("type") or "")
        body = event.get(kind) if isinstance(event.get(kind), dict) else event
        conversation = body.get("conversation_id") or event.get("conversation_id")
        if conversation:
            self.session_id = str(conversation)
        if kind == "step_update":
            step_type = str(body.get("step_type") or "")
            if body.get("text_delta") and step_type in {"agent_response", "planner_response", ""}:
                self._text_parts.append(str(body["text_delta"]))
                return []
            if body.get("thinking_delta"):
                return [{"type": "reasoning", "text": str(body["thinking_delta"])}]
            info = body.get("tool_info")
            if isinstance(info, dict) and info:
                key = str(body.get("step_index", body.get("step_id", info.get("id", len(self._tools_seen)))))
                fingerprint = json.dumps(info, sort_keys=True, default=str)
                if self._tools_seen.get(key) == fingerprint:
                    return []
                self._tools_seen[key] = fingerprint
                return [self._tool_event(info)]
            return []
        if kind == "result":
            out = []
            if self._text_parts:
                out.append({"type": "message", "text": "".join(self._text_parts)})
            if isinstance(body.get("response"), str) and body["response"]:
                self._final_text = body["response"]
            usage = body.get("usage") or {}
            self._usage = usage_record(usage.get("input_tokens"), usage.get("output_tokens"),
                                       usage.get("thinking_tokens"), usage.get("cache_read_tokens"))
            if str(body.get("status", "")).upper() == "ERROR" or body.get("error"):
                message = str(body.get("error") or "error")
                self._turn_errors.append(message)
                out.append({"type": "error", "text": message})
            return out
        if kind == "error":
            message = str(body.get("message") or body.get("error") or event)
            self._turn_errors.append(message)
            return [{"type": "error", "text": message}]
        return []

    def final_text(self) -> str:
        return self._final_text or "".join(self._text_parts).strip()

    @staticmethod
    def _tool_event(info: dict[str, Any]) -> dict[str, Any]:
        name = str(info.get("name") or info.get("tool_name") or "tool")
        arguments = info.get("args") or info.get("arguments") or info.get("input") or {}
        output = info.get("output") or info.get("result") or ""
        if name in {"run_command", "command"}:
            command = arguments.get("CommandLine") or arguments.get("command") if isinstance(arguments, dict) else arguments
            return {"type": "command", "text": str(command or ""), "output": str(output),
                    "exit_code": info.get("exit_code")}
        if name in {"write_to_file", "replace_file_content", "multi_replace_file_content", "write_file", "edit_file"}:
            target = arguments.get("TargetFile") or arguments.get("path") if isinstance(arguments, dict) else ""
            return {"type": "file_change", "tool": name, "text": str(target or ""), "output": str(output)}
        return {"type": "tool", "tool": name, "text": arguments, "output": str(output)}
