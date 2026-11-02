"""Q1 step 1: in recorded Codex → NanoGPT requests, which tool calls came back as text?

The recording proxy kept request bodies only, so a reply that NanoGPT returned as plain text
shows up in the next request's history as an assistant message holding Qwen's tool-call markup
(``<tool_call><function=NAME>…``). For every recorded session this counts, per declared tool kind
(plain function, member of a ``namespace`` tool, undeclared), the calls that arrived as real
``function_call`` items and the ones that arrived as text.

    uv run python -m studies.thursday.codex_leaks [model_requests folders…]
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
from pathlib import Path

FUNCTION = re.compile(r"<function=([^>\s]+)>")
DEFAULT_GLOB = "output/workbench/20261015T*/run-*/**/model_requests"


def _body(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(record.get("codex_request"), dict):
        return record["codex_request"]
    try:
        return json.loads(record.get("raw_body_utf8") or "")
    except ValueError:
        return None


def _declared(tools: list[dict]) -> tuple[set[str], set[str]]:
    plain, namespaced = set(), set()
    for tool in tools:
        if tool.get("type") == "namespace":
            for member in tool.get("tools") or []:
                namespaced.update({member.get("name", ""), f"{tool.get('name')}__{member.get('name')}"})
        elif tool.get("name"):
            plain.add(tool["name"])
    return plain, namespaced


def scan(folder: Path) -> dict:
    models, plain, namespaced, seen = set(), set(), set(), set()
    calls, leaks = collections.Counter(), collections.Counter()
    leaked_names = collections.Counter()
    for path in sorted(folder.glob("*.json")):
        body = _body(path)
        if not body or not isinstance(body.get("input"), list):
            continue
        models.add(body.get("model"))
        p, n = _declared(body.get("tools") or [])
        plain |= p
        namespaced |= n
        for item in body["input"]:
            kind = item.get("type")
            if kind in ("function_call", "custom_tool_call"):
                key = ("call", item.get("call_id") or item.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                calls["namespace" if item.get("namespace") else "custom" if kind == "custom_tool_call" else "plain"] += 1
            elif kind == "message" and item.get("role") == "assistant":
                text = "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))
                names = FUNCTION.findall(text)
                if "<tool_call>" not in text and not names:
                    continue
                key = ("leak", item.get("id") or hashlib.sha1(text.encode()).hexdigest())
                if key in seen:
                    continue
                seen.add(key)
                for name in names or ["?"]:
                    leaked_names[name] += 1
                    leaks["namespace" if name in namespaced else "plain" if name in plain else "undeclared"] += 1
    return {"folder": folder.as_posix(), "models": sorted(m for m in models if m),
            "declared": {"plain": len(plain), "namespace members": len(namespaced) // 2},
            "calls": dict(calls), "text_leaks": dict(leaks), "leaked_names": dict(leaked_names)}


def main(argv: list[str]) -> None:
    folders = [Path(a) for a in argv] or sorted(Path(".").glob(DEFAULT_GLOB))
    for folder in folders:
        row = scan(folder)
        if row["models"]:
            print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
