"""AVO harnesses H0 (raw) and H1 (tools) on plain OpenRouter chat completions.

The model, workspace, prompts, AVO tool CLIs and turn protocol (``drive_turns``)
are identical to the Codex harness. Shell commands run inside the same native
Codex sandbox profile used by Codex itself (``IsolatedRuntime.command``), so
filesystem and network isolation do not differ between harnesses. Only the
agent loop and the way tools are offered differ:

- ``tools`` (H1): native function tools ``shell``, ``read_file``, ``write_file``, ``view_image``.
- ``raw`` (H0): no tool schema; fenced ```bash blocks in the reply are executed.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from avo.analysis.run_trace import RunTraceRecorder
from avo.client.codex_oauth_agent import CodexOAuthConfig, drive_turns
from avo.client.model_provider import resolve_model
from avo.client.openrouter_chat import OpenRouterChat, image_part
from avo.core.agent_backend import AgentGateway, AgentRunResult, AgentToolServer
from avo.core.tool_gateway import FileToolServer
from avo.isolation import IsolatedRuntime, IsolationError, runtime_root
from studies.codex_agent.session import _find_codex_bin

MAX_STEPS_PER_TURN = 300
CONTEXT_CHARS = int(os.environ.get("HARNESS_AVO_CONTEXT_CHARS", "400000"))
DEFAULT_COMMAND_SECONDS = 600
OUTPUT_HEAD, OUTPUT_TAIL = 4_000, 12_000
# A block opened with N backticks closes only at a line holding exactly N backticks,
# so file content containing ``` can be written with a longer fence.
_BASH_BLOCK = re.compile(r"^(`{3,})(?:bash|sh|shell)[ \t]*\n([\s\S]*?)^\1[ \t]*$", re.MULTILINE)
# Candidate evaluation and solver self-checks block until a whole run finishes.
_LONG_COMMAND = re.compile(r"avo_evolve_tool\.py\s+evaluate\b|avo_tool\.py\s+evaluate_solver\b")

TOOLS_PROTOCOL = """

# Harness tools

You act through function tools. `shell` runs one command in your workspace (working
directory) and returns its exit code and output. `read_file` and `write_file` read and
replace workspace files; `view_image` shows you a PNG from the workspace. A turn ends
when you reply without calling a tool, so keep calling tools until the work is done."""

RAW_PROTOCOL = """

# Harness protocol

You have no function-calling interface. To run commands, put them in fenced blocks:

```bash
python avo_tool.py status
```

Every ```bash block in your reply is executed in your workspace (working directory), in
order, and the output is returned in the next message. Write files with shell
here-documents (cat > file.py <<'EOF' ... EOF). If the command itself contains a line of
three backticks, open and close the block with four (````bash ... ````). A turn ends when
you reply without any bash block, so keep issuing commands until the work is done."""

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


class OpenRouterShellAgent:
    """One persistent OpenRouter conversation controlling the AVO workspace."""

    def __init__(self, config: CodexOAuthConfig) -> None:
        if config.harness not in {"raw", "tools"}:
            raise ValueError("OpenRouterShellAgent implements the raw and tools harnesses")
        self.config = config
        self.provider, self.provider_model = resolve_model(config.model)
        if self.provider != "openrouter":
            raise ValueError("The raw and tools harnesses require an openrouter/vendor/model ID")
        if config.service_tier:
            raise ValueError("OpenRouter models do not support the Codex service tier setting")

    def run(self, gateway: AgentGateway, workspace: str | Path, *,
            tool_server: AgentToolServer | None = None) -> AgentRunResult:
        artifacts = Path(self.config.analysis_dir) if self.config.analysis_dir else runtime_root() / ("a-" + uuid4().hex)
        codex_bin = _find_codex_bin(self.config.codex_bin)
        if not codex_bin:
            raise IsolationError("The Codex sandbox executable is required to isolate shell commands")
        # No authenticate_* call: the API key stays in this trusted process only.
        runtime = IsolatedRuntime(Path(workspace), artifacts, codex_bin)
        try:
            return self._run(gateway, Path(workspace).resolve(), tool_server, runtime)
        finally:
            runtime.close()

    def _run(self, gateway: AgentGateway, workspace_path: Path,
             tool_server: AgentToolServer | None, runtime: IsolatedRuntime) -> AgentRunResult:
        workspace_path.mkdir(parents=True, exist_ok=True)
        self.workspace = workspace_path
        self.runtime = runtime
        transcript_path = workspace_path / "agent_transcript.jsonl"
        trace = RunTraceRecorder(runtime.artifacts, workspace_path)
        server = tool_server or FileToolServer(gateway, workspace_path)  # type: ignore[arg-type]
        server.start()
        trace.snapshot("workspace_initialized")
        base = Path(self.config.prompt_path).resolve().read_text(encoding="utf-8").strip()
        if self.config.task_instructions.strip():
            base += "\n\n" + self.config.task_instructions.strip()
        prompt = base + (TOOLS_PROTOCOL if self.config.harness == "tools" else RAW_PROTOCOL)
        trace.start_session(
            role=self.config.session_role, model=self.config.model, effort=self.config.effort,
            codex_bin=str(runtime.codex_bin), base_instructions=prompt, ephemeral=True,
            metadata={**(self.config.session_metadata or {}), "model_provider": self.provider,
                      "provider_model": self.provider_model, "harness": self.config.harness,
                      "openrouter_provider": self.config.provider or None,
                      "command_sandbox": "codex sandbox --permission-profile avo"},
        )
        self.trace = trace
        self.chat = OpenRouterChat(self.provider_model, self.config.effort, trace.transport_root,
                                   context_chars=CONTEXT_CHARS, provider=self.config.provider)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
        run_error: BaseException | None = None
        try:
            turns, final_response = drive_turns(
                gateway, self.config, workspace_path, transcript_path, trace, self._run_turn)
        except BaseException as exc:
            run_error = exc
            raise
        finally:
            server.stop()
            trace.snapshot("run_finished")
            trace.finish_session(
                status="failed" if run_error is not None else "completed",
                error=f"{type(run_error).__name__}: {run_error}" if run_error is not None else None)
        return AgentRunResult(finish_reason=gateway.finish_reason, terminal=gateway.terminal,
                              turns=turns, final_response=final_response, transcript_path=transcript_path)

    def _run_turn(self, turn_number: int, instruction: str, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        self.trace.record_turn_input(turn_number=turn_number, turn_id=f"turn-{turn_number}",
                                     instruction=instruction, effort=self.config.effort)
        self.messages.append({"role": "user", "content": instruction})
        content = ""
        for _ in range(MAX_STEPS_PER_TURN):
            if time.monotonic() >= deadline:
                break
            tools = FUNCTION_TOOLS if self.config.harness == "tools" else None
            reply, record = self.chat.complete(self.messages, tools=tools)
            self.messages.append(reply)
            content = str(reply.get("content") or "")
            if record.get("reasoning"):
                self._item(turn_number, "reasoning", "assistant_reasoning", content=record["reasoning"])
            if content.strip():
                self._item(turn_number, "agentMessage", "assistant", content=content)
            if reply.get("tool_calls"):
                pending: list[dict[str, Any]] = []
                for call in reply["tool_calls"]:
                    function = call.get("function") or {}
                    result, image = self._function(turn_number, str(function.get("name", "")),
                                                   function.get("arguments") or "{}", deadline)
                    self.messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                    if image is not None:
                        pending.append(image)
                if pending:
                    self.messages.append({"role": "user", "content": [
                        {"type": "text", "text": "Requested image(s):"}, *pending]})
                continue
            blocks = ([match.group(2) for match in _BASH_BLOCK.finditer(content)]
                      if self.config.harness == "raw" else [])
            if blocks:
                outputs = [self._shell(turn_number, block.strip(), None, deadline) for block in blocks]
                self.messages.append({"role": "user", "content": "\n\n".join(
                    f"Command {index} output:\n{output}" for index, output in enumerate(outputs, 1))})
                continue
            return content
        return content

    def _function(self, turn_number: int, name: str, raw_arguments: str | dict,
                  deadline: float) -> tuple[str, dict | None]:
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
            if name == "shell":
                return self._shell(turn_number, str(arguments["command"]),
                                   arguments.get("timeout_seconds"), deadline), None
            path = self._workspace_path(str(arguments["path"]))
            if name == "read_file":
                return path.read_text(encoding="utf-8", errors="replace")[:200_000], None
            if name == "write_file":
                if any(part in {".avo_rpc", ".avo_evolution_rpc"} for part in path.relative_to(self.workspace).parts):
                    raise ValueError("Framework RPC directories are read-only")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(arguments["content"]), encoding="utf-8")
                self._item(turn_number, "fileChange", "tool", item={
                    "type": "fileChange", "status": "completed",
                    "changes": [{"path": path.relative_to(self.workspace).as_posix(), "kind": "write"}]})
                return f"Wrote {path.relative_to(self.workspace).as_posix()}", None
            if name == "view_image":
                if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("view_image accepts PNG files only")
                return "Image attached in the next message.", image_part(path)
            raise ValueError(f"Unknown tool: {name}")
        except (KeyError, ValueError, TypeError, OSError) as exc:
            # Paths outside the workspace are not echoed back to the model.
            return f"Error: {type(exc).__name__}: {exc if not isinstance(exc, OSError) else 'file operation failed'}", None

    def _workspace_path(self, raw: str) -> Path:
        candidate = Path(raw)
        path = (candidate if candidate.is_absolute() else self.workspace / candidate).resolve()
        if path != self.workspace and self.workspace not in path.parents:
            raise ValueError("Path must stay inside the workspace")
        return path

    def _shell(self, turn_number: int, command: str, requested: Any, deadline: float) -> str:
        remaining = max(1.0, deadline - time.monotonic())
        if _LONG_COMMAND.search(command):
            limit = remaining
        else:
            try:
                limit = float(requested) if requested else DEFAULT_COMMAND_SECONDS
            except (TypeError, ValueError):
                limit = DEFAULT_COMMAND_SECONDS
            limit = max(1.0, min(limit, remaining))
        shell = (["bash", "-c", command] if os.name != "nt"
                 else ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command])
        started = time.monotonic()
        process = subprocess.Popen(self.runtime.command(*shell), cwd=self.workspace, env=self.runtime.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != "nt")
        timed_out = False
        try:
            raw, _ = process.communicate(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            raw, _ = process.communicate()
        text = raw.decode("utf-8", errors="replace")
        if len(text) > OUTPUT_HEAD + OUTPUT_TAIL:
            text = (text[:OUTPUT_HEAD] + f"\n[... {len(text) - OUTPUT_HEAD - OUTPUT_TAIL} characters omitted ...]\n"
                    + text[-OUTPUT_TAIL:])
        status = f"timed out after {int(limit)} s" if timed_out else f"exit code {process.returncode}"
        duration = int((time.monotonic() - started) * 1000)
        self._item(turn_number, "commandExecution", "tool", item={
            "type": "commandExecution", "command": command, "aggregatedOutput": text,
            "exitCode": None if timed_out else process.returncode, "durationMs": duration,
            "status": "failed" if timed_out else "completed"})
        return f"[{status}]\n{text}"

    def _item(self, turn_number: int, item_type: str, role: str, *, content: str = "",
              item: dict | None = None) -> None:
        record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "session_id": self.trace.session_id,
                  "turn": turn_number, "turn_id": f"turn-{turn_number}", "source": "openrouter_harness",
                  "type": item_type, "role": role}
        if item is not None:
            record["item"] = item
        else:
            record["content"] = content
        self.trace.record_conversation(record)
        if item_type == "commandExecution" or item_type == "fileChange":
            self.trace.snapshot(f"turn:{turn_number}:{item_type}")


def make_agent(config: CodexOAuthConfig):
    """Select the AVO harness: codex (H2), tools (H1) or raw (H0)."""
    if config.harness == "codex":
        from avo.client.codex_oauth_agent import CodexOAuthAgent
        return CodexOAuthAgent(config)
    return OpenRouterShellAgent(config)
