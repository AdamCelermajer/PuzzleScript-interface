"""A recorded session as one conversation, read top to bottom: the system prompt split into what we
wrote (system_prompt.txt) and what the harness added, the tools offered, then every message once, in
order. Built from the calls/ folders harnesses/recorder.py writes: each request resends the history,
so only what is new in it is shown, and the model's turns come from its replies."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from harnesses.recorder import view

SKIP = {"workspace", "frames", "initial_frames", "node_modules", "model_requests", "workspace_blobs", "raw",
        "world_model_snapshots", "calls"}


def call_folders(run_dir: Path) -> list[Path]:
    """Every calls/ folder of a run that holds at least one call, outside workspaces and dot folders."""
    found = []
    for current, dirs, _files in os.walk(run_dir):
        if os.path.isfile(os.path.join(current, "calls", "0001.json")):
            found.append(Path(current) / "calls")
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
    return sorted(found)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_sent(session: Path) -> list[str]:
    """Our message of each turn (sent.jsonl), as passed to the harness."""
    rows = []
    try:
        lines = (session / "sent.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("instruction"), str):
            rows.append(row["instruction"])
    return rows


def split(text: str, ours: list[str]) -> list[dict]:
    """The text as pieces {source, text}: 'ours' where one of our texts appears in it, 'harness' around it.
    Without any of our texts on record the whole text is 'unknown'."""
    known = [o for o in ours if o and o.strip()]
    if not known:
        return [{"source": "unknown", "text": text}] if text.strip() else []
    hits = []
    for candidate in known:
        needle = candidate if candidate in text else candidate.strip()
        at = text.find(needle)
        if at >= 0:
            hits.append((at, -len(needle), needle))
    if not hits:
        return [{"source": "harness", "text": text}] if text.strip() else []
    at, _, needle = min(hits)
    pieces = [{"source": "harness", "text": text[:at]}, {"source": "ours", "text": needle},
              *split(text[at + len(needle):], known)]
    return [piece for piece in pieces if piece["text"].strip()]


GRID = re.compile(r"(grid[^\n]*:\n)(?:[ \t]*-?\d+(?:[ \t]+-?\d+)*[ \t]*(?:\n|$))+")
CHANGES = re.compile(r"changed \(\d+,\d+\) -?\d+->-?\d+(?:, \(\d+,\d+\) -?\d+->-?\d+)*")


def generic(text: str) -> str:
    """The game-specific parts of an observation as placeholders: the page is about the context."""
    return CHANGES.sub("changed <cells>", GRID.sub(r"\1<grid>\n", text))


def transcript(session: Path) -> dict:
    """The session as {session, system, tools, entries}; entries are us / model / result / note, in order."""
    records = [r for r in (read_json(p) for p in sorted((session / "calls").glob("[0-9][0-9][0-9][0-9].json")))
               if r.get("method") == "POST"]
    manifest = read_json(session / "session.json")
    try:
        system_prompt = (session / "system_prompt.txt").read_text(encoding="utf-8")
    except OSError:
        system_prompt = ""
    ours = read_sent(session)
    result = {"session": {key: manifest.get(key) for key in ("harness", "model", "role", "game_tools")},
              "system": [], "tools": [], "entries": []}
    if not records:
        return result
    first = view(records[0].get("request"))
    result["system"] = split("\n\n".join(first["system"]), [system_prompt])
    for tool in first["tools"]:
        definition = tool["definition"] if isinstance(tool["definition"], dict) else {}
        result["tools"].append({"name": tool["name"], "definition": definition})
    entries, previous, calls = result["entries"], None, {}
    for record in records:
        shown = view(record.get("request"))
        kept = 0
        if previous is not None:
            while kept < min(len(previous["messages"]), len(shown["messages"])) and \
                    previous["messages"][kept] == shown["messages"][kept]:
                kept += 1
            if kept < len(previous["messages"]):
                entries.append({"who": "note", "text": f"Here {result['session']['harness'] or 'the harness'} "
                                f"rewrote the context: only {kept} of the {len(previous['messages'])} earlier "
                                "messages were sent again (a new session or a summary)."})
            if previous["system"] != shown["system"]:
                entries.append({"who": "note", "text": "Here the system prompt changed."})
        for message in shown["messages"][kept:]:
            if message["role"] == "assistant":
                continue  # the model's own turns come from its replies, which also hold its thinking
            for part in message["parts"]:
                if part["kind"] == "tool_result":
                    of = calls.get(part.get("id"), "")
                    entries.append({"who": "result", "of": of if len(of) <= 100 else of[:100] + "…", "text": generic(part.get("text", "")),
                                    "images": part.get("images") or []})
                elif part["kind"] == "text":
                    entries.append({"who": "us", "pieces": [{**piece, "text": generic(piece["text"])}
                                                            for piece in split(part.get("text") or "", ours)]})
                elif part["kind"] == "image":
                    entries.append({"who": "us", "image": part.get("file")})
        response = record.get("response") or {}
        tool_calls = []
        for call in response.get("tool_calls") or []:
            label = f"{call.get('name')}({call.get('arguments') or ''})"
            calls[call.get("id")] = label
            tool_calls.append(label)
        entries.append({"who": "model", "thinking": response.get("reasoning") or "",
                        "text": response.get("content") or "", "tool_calls": tool_calls,
                        "error": record.get("error") or ""})
        previous = shown
    return result
