"""Readable extras for one recorded agent session: the prompts we sent and a diff for every file edit.

Only what a run already recorded is used. File edits come from the harness's raw turn records
(`raw/turn-N.jsonl` next to `agent_events.jsonl`); prompts come from `system_prompt.txt`,
`mission.md` (Harness² coach) and, for the turn-based Baseline, `transcript.jsonl` + `turns.jsonl`.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

DIFF_LIMIT = 30_000
PROMPT_LIMIT = 60_000
_raw_cache: dict[str, tuple[float, int, list[dict]]] = {}


def _read(path: Path, limit: int) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def _unified(old: str, new: str, path: str) -> str:
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(), f"a/{path.lstrip('/')}", f"b/{path.lstrip('/')}", lineterm="", n=3)
    return "\n".join(lines)


def _strip_index(diff: str) -> str:
    """OpenCode diffs start with `Index:` and a `====` rule before the usual `---`/`+++` header."""
    lines = diff.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("--- ")), 0)
    return "\n".join(lines[start:])


def _ops_from_line(line: str) -> list[dict]:
    """File operations in one raw harness line (OpenCode, Claude Code or Codex), in call order."""
    try:
        event = json.loads(line)
    except ValueError:
        return []
    if not isinstance(event, dict):
        return []
    kind = event.get("type")
    if kind == "tool_use":  # OpenCode
        part = event.get("part") or {}
        tool = part.get("tool")
        if tool not in {"edit", "write", "patch", "multiedit"}:
            return []
        state = part.get("state") or {}
        args, meta = state.get("input") or {}, state.get("metadata") or {}
        path = str(args.get("filePath") or "")
        if tool == "write":
            return [{"path": path, "content": str(args.get("content") or ""), "exists": meta.get("exists")}]
        if tool == "edit":
            diff = meta.get("diff") or (meta.get("filediff") or {}).get("patch")
            return [{"path": path, "diff": _strip_index(str(diff)) if diff else None,
                     "edits": [(str(args.get("oldString") or ""), str(args.get("newString") or ""), bool(args.get("replaceAll")))]}]
        if tool == "multiedit":
            edits = [(str(e.get("oldString") or ""), str(e.get("newString") or ""), bool(e.get("replaceAll")))
                     for e in args.get("edits") or [] if isinstance(e, dict)]
            return [{"path": path, "diff": None, "edits": edits}]
        return [{"path": path, "diff": str(args.get("patchText") or "") or None}]
    if kind == "assistant":  # Claude Code: tool_use blocks inside the assistant message
        ops = []
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, args = block.get("name"), block.get("input") or {}
            path = str(args.get("file_path") or args.get("notebook_path") or "")
            if name == "Write":
                ops.append({"path": path, "content": str(args.get("content") or ""), "exists": None})
            elif name == "Edit":
                ops.append({"path": path, "diff": None, "edits": [(str(args.get("old_string") or ""), str(args.get("new_string") or ""), bool(args.get("replace_all")))]})
            elif name == "MultiEdit":
                ops.append({"path": path, "diff": None, "edits": [(str(e.get("old_string") or ""), str(e.get("new_string") or ""), bool(e.get("replace_all")))
                                                                  for e in args.get("edits") or [] if isinstance(e, dict)]})
            elif name == "NotebookEdit":
                ops.append({"path": path, "diff": None})
        return ops
    if kind == "item.completed" and (event.get("item") or {}).get("type") == "file_change":  # Codex
        changes = (event.get("item") or {}).get("changes") or []
        diffs = []
        for change in changes:
            detail = change.get("kind") if isinstance(change.get("kind"), dict) else change
            diffs.append(str(detail.get("unified_diff") or detail.get("diff") or ""))
        return [{"path": ", ".join(str(c.get("path", "")) for c in changes), "diff": "\n".join(d for d in diffs if d) or None}]
    return []


def _raw_ops(path: Path) -> list[dict]:
    stat = path.stat()
    cached = _raw_cache.get(str(path))
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2]
    ops: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if '"tool_use"' in line or '"file_change"' in line:
                ops.extend(_ops_from_line(line))
    _raw_cache[str(path)] = (stat.st_mtime, stat.st_size, ops)
    return ops


def attach_diffs(session: Path, events: list[dict]) -> None:
    """Give each `file_change` event a readable unified diff (`diff`, plus `diff_note` when partial).

    Events carry `_turn` and `_file_index` (their position among that turn's file edits).
    Whole-file writes are diffed against the last content this session wrote to the path;
    an edit applied to known content keeps that content current.
    """
    wanted = [e for e in events if e.get("type") == "file_change" and e.get("_turn") is not None]
    raw = session / "raw"
    if not wanted or not raw.is_dir():
        return
    last_turn = max(int(e["_turn"]) for e in wanted)
    known: dict[str, str] = {}
    per_turn: dict[int, list[tuple[str, str | None]]] = {}
    for turn in range(1, last_turn + 1):
        path = raw / f"turn-{turn}.jsonl"
        if not path.is_file():
            continue
        results = []
        for op in _raw_ops(path):
            name, note = op["path"], None
            if "content" in op:
                before = known.get(name)
                if before is not None:
                    diff = _unified(before, op["content"], name)
                elif op.get("exists") is False:
                    diff = _unified("", op["content"], name)
                    note = "new file"
                else:
                    diff = _unified("", op["content"], name)
                    note = "the file's earlier content was not recorded: every line is shown as written"
                known[name] = op["content"]
            else:
                diff, edits = op.get("diff"), op.get("edits") or []
                before = known.get(name)
                if before is not None and edits:
                    after = before
                    for old, new, every in edits:
                        after = after.replace(old, new) if every else after.replace(old, new, 1)
                    known[name] = after
                    diff = diff or _unified(before, after, name)
                elif diff is None and edits:
                    # Content unknown: each replaced passage on its own.
                    diff = "\n".join(_unified(old, new, name) for old, new, _ in edits)
                if not diff:
                    note = "no diff was recorded for this edit"
            results.append((diff or "", note))
        per_turn[turn] = results
    for event in wanted:
        found = per_turn.get(int(event["_turn"]), [])
        index = int(event.get("_file_index", 0))
        if index < len(found):
            diff, note = found[index]
            event["diff"] = diff if len(diff) <= DIFF_LIMIT else diff[:DIFF_LIMIT] + "\n[truncated]"
            if note:
                event["diff_note"] = note


def session_prompts(session: Path) -> dict:
    """What we sent this session: its system prompt, a mission file, and each turn's message if recorded."""
    turns: dict[str, str] = {}
    transcript, turn_log = session / "transcript.jsonl", session / "turns.jsonl"
    if transcript.is_file() and turn_log.is_file():
        prompts = []
        for line in transcript.open(encoding="utf-8", errors="replace"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("prompt"), str):
                prompts.append(row["prompt"])
        rows = []
        for line in turn_log.open(encoding="utf-8", errors="replace"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("turn"), int):
                rows.append(row)
        position = 0
        for i, row in enumerate(rows):
            if row.get("turn_kind") == "game_action":
                if position < len(prompts):
                    turns[str(row["turn"])] = prompts[position][:PROMPT_LIMIT]
                # A transient failure is retried with the same message in the next session turn.
                retried = bool(row.get("error")) and not row.get("text") and i + 1 < len(rows) \
                    and rows[i + 1].get("turn_kind") == "game_action"
                if not retried:
                    position += 1
    return {"system": _read(session / "system_prompt.txt", PROMPT_LIMIT),
            "mission": _read(session / "mission.md", PROMPT_LIMIT),
            "turns": turns,
            "turns_recorded": transcript.is_file() and turn_log.is_file()}
