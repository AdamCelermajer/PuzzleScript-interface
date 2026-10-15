"""Claude Code harness: ``claude -p --output-format stream-json --verbose``.

The first turn creates the session with ``--session-id <uuid>``; later turns use
``--resume <uuid>``. The system prompt is passed with ``--append-system-prompt`` on
every process. Images are sent as base64 content blocks through
``--input-format stream-json`` on stdin. Claude Code refuses
``--dangerously-skip-permissions`` as root, so the container runs as ``agent``.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from harnesses.base import CliSession, usage_record

DISALLOWED_TOOLS = ("WebSearch", "WebFetch")
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


class ClaudeCodeSession(CliSession):
    harness_id = "claude-code"

    def prepare(self) -> None:
        self.binary = shutil.which("claude") or "claude"
        config_dir = self.private / "claude-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        # An empty private config dir: no user settings, memories, hooks or MCP servers.
        self.env["CLAUDE_CONFIG_DIR"] = str(config_dir)
        self.env.setdefault("DISABLE_AUTOUPDATER", "1")
        self.env.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
        self._pending: dict[str, dict[str, Any]] = {}

    def command(self, instruction: str, images: Sequence[Path]) -> list[str]:
        command = [self.binary, "-p"]
        if not images:
            command.append(instruction)
        command += ["--output-format", "stream-json", "--verbose", "--model", self.native_model,
                    "--effort", self.effort, "--dangerously-skip-permissions",
                    "--append-system-prompt", self.system_prompt]
        if images:
            command += ["--input-format", "stream-json"]
        if self.session_id:
            command += ["--resume", self.session_id]
        else:
            self.session_id = str(uuid4())
            command += ["--session-id", self.session_id]
        command += ["--disallowedTools", *DISALLOWED_TOOLS]
        return command

    def stdin_payload(self, instruction: str, images: Sequence[Path]) -> str | None:
        if not images:
            return None
        content: list[dict[str, Any]] = [{"type": "text", "text": instruction}]
        for image in images:
            media = mimetypes.guess_type(image.name)[0] or "image/png"
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": media,
                "data": base64.b64encode(image.read_bytes()).decode("ascii")}})
        return json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"

    def normalize(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        kind = event.get("type")
        if event.get("session_id"):
            self.session_id = str(event["session_id"])
        if kind == "assistant":
            out = []
            for block in (event.get("message") or {}).get("content") or []:
                block_type = block.get("type")
                if block_type == "text":
                    text = str(block.get("text") or "")
                    self._text_parts.append(text)
                    out.append({"type": "message", "text": text})
                elif block_type == "thinking":
                    out.append({"type": "reasoning", "text": str(block.get("thinking") or "")})
                elif block_type == "tool_use":
                    self._pending[str(block.get("id"))] = block
            return out
        if kind == "user":
            out = []
            content = (event.get("message") or {}).get("content") or []
            for block in content if isinstance(content, list) else []:
                if block.get("type") != "tool_result":
                    continue
                call = self._pending.pop(str(block.get("tool_use_id")), {})
                out.append(self._tool_event(call, block))
            return out
        if kind == "result":
            if isinstance(event.get("result"), str):
                self._final_text = event["result"]
            usage = event.get("usage") or {}
            self._usage = usage_record(
                int(usage.get("input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0)
                + int(usage.get("cache_read_input_tokens") or 0),
                usage.get("output_tokens"), 0, usage.get("cache_read_input_tokens"),
                cost_usd=event.get("total_cost_usd"))
            if event.get("is_error"):
                message = str(event.get("result") or event.get("subtype") or "error")
                self._turn_errors.append(message)
                return [{"type": "error", "text": message}]
        return []

    @staticmethod
    def _tool_event(call: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        name = str(call.get("name") or "tool")
        arguments = call.get("input") or {}
        output = result.get("content")
        if isinstance(output, list):
            output = "\n".join(str(part.get("text", "[" + str(part.get("type")) + "]")) for part in output)
        failed = bool(result.get("is_error"))
        if name == "Bash":
            return {"type": "command", "text": str(arguments.get("command") or ""), "output": str(output or ""),
                    "exit_code": 1 if failed else 0}
        if name in FILE_TOOLS:
            return {"type": "file_change", "tool": name,
                    "text": str(arguments.get("file_path") or arguments.get("notebook_path") or ""),
                    "output": str(output or "")}
        return {"type": "tool", "tool": name, "text": arguments, "output": str(output or ""),
                "exit_code": 1 if failed else None}
