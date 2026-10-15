"""``bare`` harness: an in-process tool-calling chat loop (the former H1 ``tools`` harness).

Native function tools ``shell``, ``read_file``, ``write_file`` and ``view_image`` act
on the workspace. Shell commands are plain ``bash -c`` subprocesses in the container
with every credential variable removed; the API key stays in this controller process.
One conversation (message list) persists across turns; a turn ends when the model
replies without a tool call.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

from harnesses.base import CREDENTIAL_ENV, CliSession, TurnResult, add_usage, kill_tree, usage_record
from harnesses.chat import OpenRouterChat, image_part

MAX_STEPS_PER_TURN = 300
CONTEXT_CHARS = int(os.environ.get("HARNESS_BARE_CONTEXT_CHARS", "400000"))
DEFAULT_COMMAND_SECONDS = 600
OUTPUT_HEAD, OUTPUT_TAIL = 4_000, 12_000
# Candidate evaluation and solver self-checks block until a whole run finishes.
_LONG_COMMAND = re.compile(r"avo_evolve_tool\.py\s+evaluate\b|avo_tool\.py\s+evaluate_solver\b")
PROTECTED_DIRS = {".avo_rpc", ".avo_evolution_rpc"}

TOOLS_PROTOCOL = """

# Harness tools

You act through function tools. `shell` runs one command in your workspace (working
directory) and returns its exit code and output. `read_file` and `write_file` read and
replace workspace files; `view_image` shows you a PNG from the workspace. A turn ends
when you reply without calling a tool, so keep calling tools until the work is done."""

FUNCTION_TOOLS = [
    {"type": "function", "function": {
        "name": "shell",
        "description": "Run one shell command in the workspace and return exit code and output.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout_seconds": {"type": "integer", "description": f"Default {DEFAULT_COMMAND_SECONDS}."},
        }, "required": ["command"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file from the workspace.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or replace a workspace file with the given content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "view_image",
        "description": "Show a PNG image from the workspace in the next message.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"], "additionalProperties": False}}},
]


class BareSession(CliSession):
    harness_id = "bare"
    chat_factory = OpenRouterChat

    def prepare(self) -> None:
        assert self.log is not None
        self.chat = self.chat_factory(self.native_model, self.effort, self.analysis_dir / "model_requests",
                                      context_chars=CONTEXT_CHARS, provider=self.pin_provider,
                                      model_provider=self.provider)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt + TOOLS_PROTOCOL}]
        self.session_id = f"bare-{self.private.name}"
        self.shell_env = {key: value for key, value in os.environ.items()
                          if key not in CREDENTIAL_ENV and not key.endswith("_KEY_FILE")}

    def turn(self, instruction: str, images: Iterable[str | Path] = (), timeout: float | None = None) -> TurnResult:
        if not self.started or self.log is None:
            raise RuntimeError("Session has not been started")
        self.turn_number += 1
        number = self.turn_number
        self._text_parts, self._final_text, self._usage, self._turn_errors = [], "", {}, []
        events: list[dict[str, Any]] = []
        raw = self.log.raw_path(number)
        deadline = time.monotonic() + timeout if timeout is not None else float("inf")

        def emit(kind: str, **fields: Any) -> None:
            assert self.log is not None
            events.append(self.log.write(turn=number, type=kind, session=self.session_id, **fields))

        content: Any = instruction
        image_paths = [Path(image).resolve() for image in images]
        if image_paths:
            content = [{"type": "text", "text": instruction}, *[image_part(path) for path in image_paths]]
            for path in image_paths:
                emit("image", text=str(path))
        self.messages.append({"role": "user", "content": content})
        timed_out = False
        error = ""
        try:
            for _ in range(MAX_STEPS_PER_TURN):
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                reply, record = self.chat.complete(self.messages, tools=FUNCTION_TOOLS)
                self.messages.append(reply)
                with raw.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"reply": reply, "usage": record.get("usage"),
                                             "provider": record.get("provider")}, default=str) + "\n")
                usage = record.get("usage") or {}
                details = usage.get("completion_tokens_details") or {}
                prompt_details = usage.get("prompt_tokens_details") or {}
                add_usage(self._usage, usage_record(usage.get("prompt_tokens"), usage.get("completion_tokens"),
                                                    details.get("reasoning_tokens"), prompt_details.get("cached_tokens"),
                                                    cost_usd=usage.get("cost")))
                if record.get("reasoning"):
                    emit("reasoning", text=record["reasoning"])
                text = str(reply.get("content") or "")
                if text.strip():
                    emit("message", text=text)
                self._final_text = text
                if not reply.get("tool_calls"):
                    break
                pending: list[dict] = []
                for call in reply["tool_calls"]:
                    function = call.get("function") or {}
                    result, image = self._function(emit, str(function.get("name", "")),
                                                   function.get("arguments") or "{}", deadline)
                    self.messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                    if image is not None:
                        pending.append(image)
                if pending:
                    self.messages.append({"role": "user", "content": [
                        {"type": "text", "text": "Requested image(s):"}, *pending]})
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._turn_errors.append(error)
        return self._finish_turn(number, events, 1 if error else 0, timed_out, error, timeout)

    # -- tools ---------------------------------------------------------------------
    def _function(self, emit, name: str, raw_arguments: str | dict, deadline: float) -> tuple[str, dict | None]:
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
            if name == "shell":
                return self._shell(emit, str(arguments["command"]), arguments.get("timeout_seconds"), deadline), None
            path = self._workspace_path(str(arguments["path"]))
            relative = path.relative_to(self.workspace).as_posix()
            if name == "read_file":
                text = path.read_text(encoding="utf-8", errors="replace")[:200_000]
                emit("tool", tool="read_file", text=relative, output=text)
                return text, None
            if name == "write_file":
                if any(part in PROTECTED_DIRS for part in path.relative_to(self.workspace).parts):
                    raise ValueError("Framework RPC directories are read-only")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(arguments["content"]), encoding="utf-8")
                emit("file_change", tool="write_file", text=relative)
                return f"Wrote {relative}", None
            if name == "view_image":
                if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("view_image accepts PNG files only")
                emit("image", tool="view_image", text=relative)
                return "Image attached in the next message.", image_part(path)
            raise ValueError(f"Unknown tool: {name}")
        except (KeyError, ValueError, TypeError, OSError) as exc:
            message = f"Error: {type(exc).__name__}: {exc if not isinstance(exc, OSError) else 'file operation failed'}"
            emit("tool", tool=name or "unknown", text=str(raw_arguments)[:2000], output=message, exit_code=1)
            return message, None

    def _workspace_path(self, raw: str) -> Path:
        candidate = Path(raw)
        path = (candidate if candidate.is_absolute() else self.workspace / candidate).resolve()
        if path != self.workspace and self.workspace not in path.parents:
            raise ValueError("Path must stay inside the workspace")
        return path

    def shell_command(self, command: str) -> list[str]:
        if os.name == "nt":
            return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
        return ["bash", "-c", command]

    def _shell(self, emit, command: str, requested: Any, deadline: float) -> str:
        remaining = max(1.0, deadline - time.monotonic())
        if _LONG_COMMAND.search(command):
            limit = remaining
        else:
            try:
                limit = float(requested) if requested else DEFAULT_COMMAND_SECONDS
            except (TypeError, ValueError):
                limit = DEFAULT_COMMAND_SECONDS
            limit = max(1.0, min(limit, remaining))
        process = subprocess.Popen(self.shell_command(command), cwd=self.workspace, env=self.shell_env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != "nt")
        timed_out = False
        try:
            output, _ = process.communicate(timeout=None if limit == float("inf") else limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(process)
            output, _ = process.communicate()
        text = output.decode("utf-8", errors="replace")
        if len(text) > OUTPUT_HEAD + OUTPUT_TAIL:
            text = (text[:OUTPUT_HEAD] + f"\n[... {len(text) - OUTPUT_HEAD - OUTPUT_TAIL} characters omitted ...]\n"
                    + text[-OUTPUT_TAIL:])
        status = f"timed out after {int(limit)} s" if timed_out else f"exit code {process.returncode}"
        emit("command", text=command, output=text, exit_code=None if timed_out else process.returncode)
        return f"[{status}]\n{text}"
