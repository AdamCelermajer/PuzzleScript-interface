"""Direct-player harnesses H0 (raw) and H1 (tools) on plain OpenRouter chat completions.

Same contract as ``CodexGameSession``: one persistent conversation per episode,
the same base instructions, the same reply parser and the same audited note
workspace. Only the way the model reaches its tools differs:

- ``tools`` (H1): list_notes/read_note/write_note as native function tools.
- ``raw`` (H0): no tool schema; note tags in the reply text are executed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from avo.client.model_provider import resolve_model
from avo.client.openrouter_chat import OpenRouterChat, image_part
from studies.codex_agent.note_server import TOOLS as NOTE_TOOLS, NoteWorkspace
from studies.codex_agent.session import (
    WORLD_MODEL_PROMPT, CodexSessionConfig, _response_json, game_instructions, parse_action_reply,
)

MAX_TOOL_ROUNDS = 16

RAW_NOTE_PROTOCOL = """

You have no function-calling interface. Use the note tools by writing these tags in your reply:
<list_notes/>
<read_note path="strategy.md"/>
<write_note path="strategy.md">
full new file content
</write_note>
Every tag in a reply is executed in order and the results are returned to you in the next
message. You may put your final action JSON after the tags in the same reply; the tags are
executed first and then the action is taken."""

_TAG = re.compile(
    r'<list_notes\s*/>|<read_note\s+path="([^"]*)"\s*/>|<write_note\s+path="([^"]*)"\s*>\n?([\s\S]*?)</write_note>')


def function_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": tool["name"], "description": tool["description"],
                                              "parameters": tool["inputSchema"]}} for tool in tools]


class OpenRouterGameSession:
    """One persistent OpenRouter conversation for one game episode."""

    def __init__(self, config: CodexSessionConfig, working_directory: str | Path,
                 artifact_directory: str | Path | None = None) -> None:
        if config.harness not in {"raw", "tools"}:
            raise ValueError("OpenRouterGameSession implements the raw and tools harnesses")
        self.model_provider, self.provider_model = resolve_model(config.model)
        if self.model_provider not in {"openrouter", "nanogpt"}:
            raise ValueError("The raw and tools harnesses require an OpenRouter or NanoGPT model ID")
        self.config = config
        self.working_directory = Path(working_directory)
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self.artifact_directory = Path(artifact_directory or self.working_directory.parent)
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        self.session_log_path = self.artifact_directory / "model_session.jsonl"
        self.notes = (NoteWorkspace(self.working_directory, self.artifact_directory / "note_history")
                      if config.workspace_enabled else None)
        self.chat: OpenRouterChat | None = None
        self.messages: list[dict[str, Any]] = []
        self._turn = 0

    def __enter__(self) -> "OpenRouterGameSession":
        self.chat = OpenRouterChat(self.provider_model, self.config.effort,
                                   self.artifact_directory / "model_requests", provider=self.config.provider,
                                   **({"model_provider": self.model_provider} if self.model_provider != "openrouter" else {}))
        instructions = game_instructions(self.config.workspace_enabled)
        if self.notes is not None and self.config.harness == "raw":
            instructions += RAW_NOTE_PROTOCOL
        self.messages = [{"role": "system", "content": instructions}]
        (self.artifact_directory / "isolation_manifest.json").write_text(json.dumps({
            "harness": self.config.harness, "transport": f"{self.model_provider} chat completions", "model_provider": self.model_provider,
            "model": self.provider_model, "effort_requested": self.chat.effort,
            "effort_sent": self.chat.effort_sent, "context_chars": self.chat.context_chars,
            "openrouter_provider": self.config.provider or None,
            "context_policy": "newest frame image only; oldest exchanges dropped over budget",
            "model_visible_note_tools": (["list_notes", "read_note", "write_note"] if self.notes else []),
            "note_tool_transport": ("native function tools" if self.config.harness == "tools" else "text tags")
                                   if self.notes else None,
            "model_has_filesystem_or_shell": False,
            "base_instructions": instructions,
            "prompt_omits_game_id": True, "prompt_omits_game_title": True,
            "prompt_omits_action_meanings": True,
        }, indent=2), encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.chat = None

    def next_action(self, prompt: str, image_path: str | Path | None = None) -> dict[str, str]:
        self._turn += 1
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image_path is not None:
            content.append(image_part(image_path))
        self.messages.append({"role": "user", "content": content})
        for round_number in range(1, MAX_TOOL_ROUNDS + 2):
            last_round = round_number > MAX_TOOL_ROUNDS
            reply = self._call("game_action", round_number, allow_tools=not last_round)
            text = str(reply.get("content") or "")
            if reply.get("tool_calls"):
                # Every call must be answered or the next request is malformed.
                for call in reply["tool_calls"]:
                    function = call.get("function") or {}
                    result = (json.dumps({"error": "Tool round limit reached; reply with the action."})
                              if last_round or self.notes is None else
                              self._run_note(str(function.get("name", "")), function.get("arguments") or "{}"))
                    self.messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                if last_round:
                    raise ValueError("Note-tool round limit reached without an action")
                continue
            if self.notes is not None and self.config.harness == "raw" and _TAG.search(text):
                results = self._run_tags(text)
                remainder = _TAG.sub("", text).strip()
                try:
                    return parse_action_reply(remainder)
                except ValueError:
                    pass
                if last_round:
                    raise ValueError("Note-tool round limit reached without an action")
                self.messages.append({"role": "user", "content": "Tool results:\n" + results})
                continue
            return parse_action_reply(text)
        raise ValueError("Note-tool round limit reached without an action")

    def note_tool_count(self) -> int:
        audit_path = self.working_directory / "tool_calls.jsonl"
        if not audit_path.exists():
            return 0
        return sum(1 for line in audit_path.read_text(encoding="utf-8").splitlines() if line)

    def final_world_model(self) -> dict[str, object]:
        self.messages.append({"role": "user", "content": WORLD_MODEL_PROMPT})
        reply = self._call("final_world_model", 1, allow_tools=False)
        payload = _response_json(str(reply.get("content") or ""))
        if not isinstance(payload, dict):
            raise ValueError("World model response must be a JSON object")
        return payload

    def _call(self, turn_kind: str, round_number: int, *, allow_tools: bool) -> dict[str, Any]:
        if self.chat is None:
            raise RuntimeError("OpenRouter game session has not been started")
        tools = None
        if self.notes is not None and self.config.harness == "tools":
            # Keep the schema stable across rounds; tool_choice=none closes the round limit.
            tools = function_tools(NOTE_TOOLS)
        reply, record = self.chat.complete(self.messages, tools=tools,
                                           tool_choice=None if allow_tools else "none")
        self.messages.append(reply)
        with self.session_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": datetime.now().isoformat(timespec="seconds"), "turn_kind": turn_kind,
                "turn": self._turn, "round": round_number, "harness": self.config.harness,
                "content": reply.get("content"), "tool_calls": reply.get("tool_calls"), **record,
            }, default=str) + "\n")
        return reply

    def _run_note(self, name: str, raw_arguments: str | dict) -> str:
        assert self.notes is not None
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
            return json.dumps(self.notes.call(name, arguments))
        except (OSError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    def _run_tags(self, text: str) -> str:
        results = []
        for match in _TAG.finditer(text):
            if match.group(0).startswith("<list_notes"):
                results.append("list_notes -> " + self._run_note("list_notes", {}))
            elif match.group(0).startswith("<read_note"):
                results.append(f"read_note {match.group(1)} -> " + self._run_note("read_note", {"path": match.group(1)}))
            else:
                results.append(f"write_note {match.group(2)} -> " + self._run_note(
                    "write_note", {"path": match.group(2), "content": match.group(3)}))
        return "\n".join(results)


def open_game_session(config: CodexSessionConfig, working_directory: str | Path,
                      artifact_directory: str | Path | None = None):
    if config.harness == "codex":
        from studies.codex_agent.session import CodexGameSession
        return CodexGameSession(config, working_directory, artifact_directory=artifact_directory)
    return OpenRouterGameSession(config, working_directory, artifact_directory=artifact_directory)
