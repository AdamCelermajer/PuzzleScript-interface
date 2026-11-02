"""Q1 step 2: does NanoGPT return Qwen 27B's tool calls as text, and on which endpoint?

Sends tool-calling requests straight to NanoGPT (no CLI), streamed the way the CLIs stream, and
classifies each reply as a real tool call, a tool call returned as text, or no call.

- ``synthetic``: one write_note tool and a short or long note task, on the Chat endpoint (what
  OpenCode uses), the Responses endpoint (what Codex uses), Responses with the namespaced name
  ``mcp__codex_notes__write_note`` as a plain function, and Responses with the tool inside a
  Codex-style ``namespace``.
- ``replay``: a request Codex really sent just before a leaked reply (15 Oct, Baseline+), sent again
  as recorded to Responses, and converted to the same conversation on the Chat endpoint.

    uv run python -m studies.thursday.probe_tool_calls --repeats 8
"""
from __future__ import annotations

import argparse
import collections
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import dotenv_values

from harnesses.opencode import NANOGPT_BASE_URL

MODEL = "qwen/qwen3.8-27b:thinking"
OUT = Path("output/thursday/q1/probes.jsonl")
RECORDED = "output/workbench/20261015T012502-nano-modality-baseline-plus-fixed-714e64/run-0001/model_requests"
SYSTEM = "You keep notes for a game player. Save notes only by calling the write_note tool."
TASKS = {
    "short": "Save a note at path a.md with the content: the box moves when pushed.",
    "long": ("Write a detailed markdown note of about 40 lines about the rules of a Sokoban-like puzzle game: "
             "a table of tile codes, a list of confirmed rules and a list of open questions. "
             "Save it with write_note at path rules.md."),
}
WRITE_NOTE = {"name": "write_note", "description": "Create or replace one note file.",
              "parameters": {"type": "object", "additionalProperties": False, "required": ["path", "content"],
                             "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}}


def chat_tool(tool: dict) -> dict:
    return {"type": "function", "function": {k: tool[k] for k in ("name", "description", "parameters") if k in tool}}


def synthetic(endpoint: str, task: str, model: str = MODEL) -> tuple[str, dict]:
    if endpoint == "chat":
        return "chat", {"model": model, "stream": True, "stream_options": {"include_usage": True}, "tool_choice": "auto",
                        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": TASKS[task]}],
                        "tools": [chat_tool(WRITE_NOTE)]}
    tool = {"type": "function", "strict": False, **WRITE_NOTE}
    if endpoint == "responses-namespace":
        tool = {"type": "namespace", "name": "mcp__codex_notes",
                "description": "Tools in the mcp__codex_notes namespace.", "tools": [tool]}
    elif endpoint == "responses-flat":  # the namespaced name, declared as a plain function
        tool = {**tool, "name": "mcp__codex_notes__write_note"}
    return "responses", {"model": model, "stream": True, "instructions": SYSTEM, "store": False,
                         "input": [{"type": "message", "role": "user",
                                    "content": [{"type": "input_text", "text": TASKS[task]}]}],
                         "tools": [tool], "tool_choice": "auto", "parallel_tool_calls": True,
                         "reasoning": {"effort": "high", "summary": "auto"}, "include": ["reasoning.encrypted_content"]}


def recorded_before_first_leak() -> dict:
    """The recorded request whose reply was the first leaked tool call."""
    previous = None
    for path in sorted(Path(RECORDED).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        body = record.get("codex_request") or json.loads(record.get("raw_body_utf8") or "{}")
        if not isinstance(body.get("input"), list):
            continue
        texts = ("".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))
                 for item in body["input"] if item.get("type") == "message" and item.get("role") == "assistant")
        if any("<function=" in text for text in texts):
            return previous
        previous = body
    raise SystemExit("no leak found in the recording")


def to_chat(body: dict) -> dict:
    """The same conversation for the Chat endpoint: plain functions, tool messages, no reasoning items."""
    messages = [{"role": "system", "content": body["instructions"]}] if body.get("instructions") else []
    for item in body["input"]:
        kind, role = item.get("type"), item.get("role")
        if kind == "message":
            parts = []
            for part in item.get("content") or []:
                if part.get("type") in ("input_text", "output_text"):
                    parts.append({"type": "text", "text": part.get("text", "")})
                elif part.get("type") == "input_image":
                    parts.append({"type": "image_url", "image_url": {"url": part.get("image_url")}})
            if role in ("developer", "system"):
                messages.append({"role": "system", "content": "\n".join(p.get("text", "") for p in parts)})
            elif role == "assistant":
                messages.append({"role": "assistant", "content": "".join(p.get("text", "") for p in parts)})
            else:
                messages.append({"role": "user", "content": parts})
        elif kind == "function_call":
            name = f"{item['namespace']}__{item['name']}" if item.get("namespace") else item["name"]
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": item["call_id"], "type": "function", "function": {"name": name, "arguments": item.get("arguments") or "{}"}}]})
        elif kind == "function_call_output":
            output = item.get("output")
            if isinstance(output, list):
                output = "\n".join(p.get("text", "") for p in output if isinstance(p, dict))
            messages.append({"role": "tool", "tool_call_id": item["call_id"], "content": str(output)})
    tools = []
    for tool in body.get("tools") or []:
        if tool.get("type") == "namespace":
            tools += [chat_tool({**member, "name": f"{tool['name']}__{member['name']}"}) for member in tool.get("tools") or []]
        elif tool.get("type") == "function":
            tools.append(chat_tool(tool))
    return {"model": body["model"], "stream": True, "stream_options": {"include_usage": True},
            "messages": messages, "tools": tools, "tool_choice": "auto"}


def stream(endpoint: str, body: dict, key: str) -> list[dict]:
    request = urllib.request.Request(f"{NANOGPT_BASE_URL}/{'chat/completions' if endpoint == 'chat' else 'responses'}",
                                     data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                              "Accept": "text/event-stream"})
    events = []
    with urllib.request.urlopen(request, timeout=900) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                try:
                    events.append(json.loads(line[5:].strip()))
                except ValueError:
                    pass
    return events


def read(endpoint: str, events: list[dict]) -> tuple[str, str, list[dict], dict | None, str]:
    text, reasoning, calls, usage, error = "", "", [], None, ""
    if endpoint == "chat":
        partial: dict[int, dict] = {}
        for event in events:
            usage = event.get("usage") or usage
            if event.get("error"):
                error = error or json.dumps(event["error"])[:800]
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                text += delta.get("content") or ""
                reasoning += delta.get("reasoning") or delta.get("reasoning_content") or ""
                for call in delta.get("tool_calls") or []:
                    slot = partial.setdefault(call.get("index", 0), {"name": "", "arguments": ""})
                    slot["name"] += (call.get("function") or {}).get("name") or ""
                    slot["arguments"] += (call.get("function") or {}).get("arguments") or ""
        return text, reasoning, list(partial.values()), usage, error
    items, output = [], None
    for event in events:
        kind = event.get("type", "")
        response = event.get("response") or {}
        if kind == "response.output_item.done":
            items.append(event.get("item") or {})
        elif kind in ("response.completed", "response.incomplete", "response.failed"):
            output, usage = response.get("output"), response.get("usage")
        if kind == "response.failed":
            error = json.dumps(response.get("error") or response.get("incomplete_details") or "failed")[:800]
        elif kind == "error":
            error = json.dumps(event)[:800]
    for item in output if output is not None else items:
        if item.get("type") == "message":
            text += "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))
        elif item.get("type") == "reasoning":
            reasoning += "".join(s.get("text", "") for s in (item.get("summary") or []) + (item.get("content") or [])
                                 if isinstance(s, dict))
        elif item.get("type") in ("function_call", "custom_tool_call"):
            calls.append({"name": item.get("name"), "namespace": item.get("namespace"), "arguments": item.get("arguments") or ""})
    return text, reasoning, calls, usage, error


def probe(condition: str, endpoint: str, body: dict, key: str) -> dict:
    started = time.time()
    try:
        text, reasoning, calls, usage, error = read(endpoint, stream(endpoint, body, key))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        text, reasoning, calls, usage, error = "", "", [], None, f"{type(exc).__name__}: {getattr(exc, 'code', '')} {exc}"[:500]
    outcome = ("tool call" if calls else "text leak" if "<tool_call>" in text or "<function=" in text
               else "error" if error else "no call")
    return {"condition": condition, "outcome": outcome, "calls": [c["name"] for c in calls],
            "args_chars": sum(len(c["arguments"]) for c in calls), "text": text[:3000],
            "reasoning": reasoning[-1500:], "usage": usage, "error": error, "seconds": round(time.time() - started, 1)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--parallel", type=int, default=8)
    parser.add_argument("--only", choices=("synthetic", "replay"))
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--endpoints", default="chat,responses,responses-flat,responses-namespace")
    args = parser.parse_args()
    key = dotenv_values(".env").get("NANOGPT_API_KEY")
    jobs = []
    if args.only != "replay":
        label = "" if args.model == MODEL else f" · {args.model}"
        for endpoint in args.endpoints.split(","):
            for task in TASKS:
                kind, body = synthetic(endpoint, task, args.model)
                jobs += [(f"{endpoint} · {task}{label}", kind, body)] * args.repeats
    if args.only != "synthetic":
        recorded = recorded_before_first_leak()
        jobs += [("replay · responses (as Codex sent it)", "responses", recorded)] * args.repeats
        jobs += [("replay · chat (same conversation)", "chat", to_chat(recorded))] * args.repeats
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(args.parallel) as pool, OUT.open("a", encoding="utf-8") as out:
        for row in pool.map(lambda job: probe(job[0], job[1], job[2], key), jobs):
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{row['condition']:42s} {row['outcome']:10s} {row['seconds']:6.1f}s {row['error'][:120]}", flush=True)
    summary = collections.defaultdict(collections.Counter)
    for line in OUT.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        summary[row["condition"]][row["outcome"]] += 1
    print("\nAll probes so far:")
    for condition, counts in sorted(summary.items()):
        print(f"  {condition:42s} " + ", ".join(f"{k} {v}" for k, v in counts.most_common()))


if __name__ == "__main__":
    main()
