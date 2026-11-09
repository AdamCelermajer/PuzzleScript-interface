"""A session for ``opencode import``, built from one recorded request (``calls/NNNN.json``).

OpenCode then sends exactly those messages again, and its loop and compaction work as if the session
had never stopped: the conversation is its own, not something added behind its back.
"""
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any

MEDIA_NOTE = "Attached media from tool result:"
SAVED_IMAGE = re.compile(r"\[image saved as ([^\]]+)\]")
VERSION = "1.19.5"


def _text(content: Any) -> str:
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return "" if content is None else str(content)


def _attachment(part: dict, images: Path) -> dict | None:
    """A tool's picture: the recorder saved it next to the call and left its name in the request."""
    found = SAVED_IMAGE.search(str((part.get("image_url") or {}).get("url", "")))
    if not found or not (images / found[1]).is_file():
        return None
    data = base64.b64encode((images / found[1]).read_bytes()).decode()
    return {"type": "file", "mime": "image/png", "filename": found[1], "url": f"data:image/png;base64,{data}"}


class _Ids:
    """OpenCode orders messages and parts by id; these all sort before any id it creates afterwards."""

    def __init__(self) -> None:
        self.number = 0

    def __call__(self, prefix: str) -> str:
        self.number += 1
        return f"{prefix}_{self.number:012x}{'0' * 14}"


def session_export(messages: list[dict], *, session_id: str, directory: str, provider: str, model: str,
                   images: Path, last_usage: dict | None = None) -> dict:
    """``messages`` as OpenCode's export format. ``last_usage`` goes on the last answer: OpenCode reads it
    to decide when to compact."""
    new_id = _Ids()
    now = int(time.time() * 1000)
    tokens = {"total": 0, "input": 0, "output": 0, "reasoning": 0, "cache": {"write": 0, "read": 0}}
    conversation = [message for message in messages if message.get("role") != "system"]
    results = {str(m.get("tool_call_id")): m for m in conversation if m.get("role") == "tool"}
    out: list[dict] = []
    parent = ""
    answers: list[dict] = []
    last_tool_parts: list[dict] = []
    for index, message in enumerate(conversation):
        stamp = now - (len(conversation) - index) * 1000
        role = message.get("role")
        if role == "user":
            content = message.get("content")
            if isinstance(content, list) and _text(content).startswith(MEDIA_NOTE):
                # OpenCode writes this message itself from the tool's attachments.
                reads = [p for p in last_tool_parts if p["tool"] == "read"] or last_tool_parts
                files = [a for a in (_attachment(p, images) for p in content if p.get("type") == "image_url") if a]
                if reads and files:
                    reads[-1]["state"]["attachments"] = [
                        {**file, "id": new_id("prt"), "sessionID": session_id, "messageID": reads[-1]["messageID"]}
                        for file in files]
                continue
            message_id = new_id("msg")
            parent = message_id
            out.append({"info": {"role": "user", "time": {"created": stamp}, "agent": "build",
                                 "model": {"providerID": provider, "modelID": model}, "summary": {"diffs": []},
                                 "id": message_id, "sessionID": session_id},
                        "parts": [{"type": "text", "text": _text(content), "id": new_id("prt"),
                                   "sessionID": session_id, "messageID": message_id}]})
        elif role == "assistant":
            message_id = new_id("msg")
            base = {"sessionID": session_id, "messageID": message_id}
            calls = message.get("tool_calls") or []
            details = {"openrouter": {"reasoning_details": message["reasoning_details"]}} if message.get("reasoning_details") else None
            parts: list[dict] = [{"type": "step-start", "id": new_id("prt"), **base}]
            if message.get("reasoning"):
                parts.append({"type": "reasoning", "text": str(message["reasoning"]), "time": {"start": stamp, "end": stamp},
                              **({"metadata": details} if details else {}), "id": new_id("prt"), **base})
            if _text(message.get("content")):
                parts.append({"type": "text", "text": _text(message.get("content")), "time": {"start": stamp, "end": stamp},
                              "id": new_id("prt"), **base})
            last_tool_parts = []
            for call in calls:
                function = call.get("function") or {}
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except ValueError:
                    arguments = {}
                output = _text((results.get(str(call.get("id"))) or {}).get("content"))
                part = {"type": "tool", "tool": function.get("name"), "callID": call.get("id"),
                        "state": {"status": "completed", "input": arguments, "output": output,
                                  "metadata": {"output": output, "truncated": False}, "title": str(function.get("name")),
                                  "time": {"start": stamp, "end": stamp}},
                        **({"metadata": details} if details else {}), "id": new_id("prt"), **base}
                parts.append(part)
                last_tool_parts.append(part)
            finish = "tool-calls" if calls else "stop"
            parts.append({"reason": finish, "type": "step-finish", "tokens": tokens, "cost": 0, "id": new_id("prt"), **base})
            info = {"parentID": parent, "role": "assistant", "mode": "build", "agent": "build",
                    "path": {"cwd": directory, "root": "/"}, "cost": 0, "tokens": tokens, "modelID": model,
                    "providerID": provider, "time": {"created": stamp, "completed": stamp}, "finish": finish,
                    "id": message_id, "sessionID": session_id}
            answers.append(info)
            out.append({"info": info, "parts": parts})
    if answers and last_usage:
        answers[-1]["tokens"] = {
            "total": int(last_usage.get("total_tokens") or 0), "input": int(last_usage.get("prompt_tokens") or 0),
            "output": int(last_usage.get("completion_tokens") or 0), "reasoning": 0, "cache": {"write": 0, "read": 0}}
    return {"info": {"id": session_id, "slug": "restored", "projectID": "global", "directory": directory,
                     "path": directory.lstrip("/"), "title": "Restored session", "agent": "build",
                     "model": {"id": model, "providerID": provider, "variant": "default"}, "version": VERSION,
                     "summary": {"additions": 0, "deletions": 0, "files": 0}, "cost": 0,
                     "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
                     "permission": [{"permission": name, "pattern": "*", "action": "deny"}
                                    for name in ("question", "plan_enter", "plan_exit")],
                     "time": {"created": now - (len(conversation) + 1) * 1000, "updated": now}},
            "messages": out}
