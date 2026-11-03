"""A recorded session read top to bottom: the system prompt split into what we wrote (system_prompt.txt)
and what the harness added, the tools offered, then one item per model call: what was new in its request
and the model's answer. Built from the calls/ folders harnesses/recorder.py writes: each request resends
the history, so only what is new in it is shown."""
from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path

from harnesses.recorder import view

# How each API carries the system prompt: a message role, or (Anthropic) a field of its own.
SYSTEM_ROLE = {"chat-completions": "system", "anthropic-messages": "system field (not a message)",
               "openai-responses": "developer"}
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


@functools.lru_cache(maxsize=4096)
def _digest(path: str) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return path


def _by_content(value, folder: Path):
    if isinstance(value, dict):
        if value.get("kind") == "image" and value.get("file"):
            return {**value, "file": _digest(str(folder / value["file"]))}
        if value.get("kind") == "tool_result" and value.get("images"):
            value = {**value, "images": [_digest(str(folder / name)) for name in value["images"]]}
        return {key: _by_content(item, folder) for key, item in value.items()}
    if isinstance(value, list):
        return [_by_content(item, folder) for item in value]
    return value


def kept_messages(previous: list[dict], current: list[dict], folder: Path) -> int:
    """How many of the previous request's messages the current one sends again unchanged. Every call
    saves its images under its own name (0003-image-1.png, 0004-image-1.png), so images compare by content."""
    kept = 0
    while kept < min(len(previous), len(current)) and (
            previous[kept] == current[kept]
            or _by_content(previous[kept], folder) == _by_content(current[kept], folder)):
        kept += 1
    return kept


def summary_requests(records: list[dict], views: list[dict]) -> list[int]:
    """The requests whose answer is a summary of the conversation (a compaction): the next request drops
    the earlier messages and sends that answer again in their place."""
    found = []
    for number in range(1, len(records) - 1):
        answer = ((records[number].get("response") or {}).get("content") or "").strip()
        later = views[number + 1]["messages"]
        resent = any(answer and part.get("kind") == "text" and (part.get("text") or "").strip() == answer
                     for message in later if message["role"] == "assistant" for part in message["parts"])
        if resent and len(later) < len(views[number - 1]["messages"]):
            found.append(number)
    return found


def built_from(records: list[dict], views: list[dict], number: int, summaries: set[int], harness: str,
               ours: list[str]) -> list[dict]:
    """Each part of one request, {part, content, source}: where it comes from among the earlier calls'
    answers, our game's tool results, our messages and the harness's own texts."""
    by_text, by_tool = {}, {}
    for earlier in range(number):
        response = records[earlier].get("response") or {}
        if (response.get("content") or "").strip():
            by_text[response["content"].strip()] = earlier
        for call in response.get("tool_calls") or []:
            by_tool[call.get("id")] = earlier
    call_of = lambda index: records[index].get("call")
    shown = views[number]
    last_game = max((i for i in range(number) if i not in summaries and views[i]["system"] == shown["system"]),
                    default=None)
    rows = [{"part": "system prompt + tools", "content": f"{sum(len(s) for s in shown['system']):,} characters; "
             f"tools {', '.join(t['name'] for t in shown['tools']) or 'none'}",
             "source": f"the same as call {call_of(last_game)}" if last_game is not None else "new"}]
    for index, message in enumerate(shown["messages"], 1):
        texts = [p.get("text") or "" for p in message["parts"] if p.get("kind") == "text"]
        tools = [p for p in message["parts"] if p.get("kind") == "tool_call"]
        thinking = any(p.get("kind") == "reasoning" for p in message["parts"])
        text = "\n".join(texts).strip()
        if message["role"] == "assistant":
            earlier = by_text.get(text) if text else next((by_tool[t.get("id")] for t in tools if t.get("id") in by_tool), None)
            content = ("thinking + " if thinking else "") + (text[:80] + ("…" if len(text) > 80 else "") if text else
                                                              ", ".join(f"{t.get('name')}({t.get('arguments') or ''})" for t in tools))
            source = ("unknown" if earlier is None else f"the model's answer in call {call_of(earlier)}"
                      + (" (the compaction summary)" if earlier in summaries else ""))
        elif any(p.get("kind") == "tool_result" for p in message["parts"]):
            result = next(p for p in message["parts"] if p.get("kind") == "tool_result")
            earlier = by_tool.get(result.get("id"))
            content = (result.get("text") or "")[:80].replace("\n", " ") + "…"
            source = f"the tool's result for the move in call {call_of(earlier)}" if earlier is not None else "a tool's result"
        else:
            content = text[:80] + ("…" if len(text) > 80 else "")
            written_by_us = any(piece["source"] == "ours" for piece in split(text, ours))
            source = "us" if written_by_us else f"{harness}: a fixed text of its own"
        rows.append({"part": f"message {index}, {message['role']}", "content": content, "source": source})
    return rows


def transcript(session: Path) -> dict:
    """The session as {session, system, tools, calls}: one item per model call, in order, each with what
    was new in its request (sent), the model's answer and notes (a compaction, a rewritten context)."""
    records = [r for r in (read_json(p) for p in sorted((session / "calls").glob("[0-9][0-9][0-9][0-9].json")))
               if r.get("method") == "POST"]
    manifest = read_json(session / "session.json")
    try:
        system_prompt = (session / "system_prompt.txt").read_text(encoding="utf-8")
    except OSError:
        system_prompt = ""
    ours = read_sent(session)
    result = {"session": {key: manifest.get(key) for key in ("harness", "model", "role", "game_tools")},
              "system": [], "system_role": "", "tools": [], "calls": [], "key_calls": []}
    if not records:
        return result
    first = view(records[0].get("request"))
    result["system"] = split("\n\n".join(first["system"]), [system_prompt])
    result["system_role"] = SYSTEM_ROLE.get(first["dialect"], first["dialect"])
    for tool in first["tools"]:
        definition = tool["definition"] if isinstance(tool["definition"], dict) else {}
        result["tools"].append({"name": tool["name"], "definition": definition})
    harness = result["session"]["harness"] or "the harness"
    views = [view(record.get("request")) for record in records]
    summaries = set(summary_requests(records, views))
    previous, labels, replied = None, {}, set()
    for number, (record, shown) in enumerate(zip(records, views)):
        notes, sent, kept, rewritten = [], [], 0, False
        if previous is not None:
            kept = kept_messages(previous["messages"], shown["messages"], session / "calls")
            rewritten = kept < len(previous["messages"])
            if number in summaries:
                notes.append(f"Compaction 1/2: {harness} asks the model to summarize the conversation so far, in a "
                             "separate request with its own system prompt and no tools. The answer is the summary.")
            elif number - 1 in summaries:
                notes.append(f"Compaction 2/2: the game goes on. The {len(views[number - 2]['messages'])} earlier "
                             f"messages are no longer sent; {harness} sends the summary in their place.")
            elif rewritten:
                notes.append(f"{harness} rewrote the context: only {kept} of the {len(previous['messages'])} "
                             "earlier messages were sent again.")
            if previous["system"] != shown["system"]:
                sent.append({"who": "system", "text": "\n\n".join(shown["system"])})
        for message in shown["messages"][kept:]:
            if message["role"] == "assistant":
                # The model's answer to the previous call is that call's row; an assistant message it never
                # wrote is the harness's, and after a rewrite earlier answers come back as new messages.
                text = "\n".join(p.get("text") or "" for p in message["parts"] if p.get("kind") == "text").strip()
                if text and text not in replied:
                    sent.append({"who": "model", "added": True, "text": text, "thinking": "", "tool_calls": []})
                elif rewritten:
                    sent.append({"who": "model", "resent": True, "text": text,
                                 "thinking": "\n".join(p.get("text") or "" for p in message["parts"]
                                                       if p.get("kind") == "reasoning"),
                                 "tool_calls": [f"{p.get('name')}({p.get('arguments') or ''})"
                                                for p in message["parts"] if p.get("kind") == "tool_call"]})
                continue
            for part in message["parts"]:
                if part["kind"] == "tool_result":
                    of = labels.get(part.get("id"), "")
                    sent.append({"who": "result", "role": message["role"], "of": of if len(of) <= 100 else of[:100] + "…",
                                 "text": part.get("text", ""), "images": part.get("images") or []})
                elif part["kind"] == "text":
                    sent.append({"who": "us", "role": message["role"],
                                 "pieces": split(part.get("text") or "", ours)})
                elif part["kind"] == "image":
                    sent.append({"who": "us", "role": message["role"], "image": part.get("file")})
        response = record.get("response") or {}
        tool_calls = []
        for call in response.get("tool_calls") or []:
            label = f"{call.get('name')}({call.get('arguments') or ''})"
            labels[call.get("id")] = label
            tool_calls.append(label)
        replied.add((response.get("content") or "").strip())
        result["calls"].append({
            "call": record.get("call"), "compaction": number in summaries, "notes": notes, "sent": sent,
            "built_from": built_from(records, views, number, summaries, harness, ours) if number - 1 in summaries else [],
            "answer": {"thinking": response.get("reasoning") or "", "text": response.get("content") or "",
                       "tool_calls": tool_calls, "error": record.get("error") or ""}})
        previous = shown
    # The calls worth reading first: the first three, then the first compaction and the call after it
    # (without one, each call with a note or a changed system prompt).
    first_summary = min(summaries) if summaries else None
    result["key_calls"] = sorted({r.get("call") for r in records[:3]} | (
        {records[first_summary].get("call"), records[first_summary + 1].get("call")} if first_summary is not None
        else {c["call"] for c in result["calls"] if c["notes"] or any(s["who"] == "system" for s in c["sent"])}))
    return result
