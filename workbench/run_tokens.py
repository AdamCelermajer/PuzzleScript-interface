"""Tokens a run used, summed over every model session recorded under its folder.

One convention for every source: `input` counts all prompt tokens, cache hits included, and `cached` is
the cache-hit part of it; `output` counts all generated tokens, reasoning included, and `reasoning` is
that part of it; `total` = input + output. OpenCode reports cache reads apart from input and reasoning
apart from output (its `tokens.total` is the sum of all buckets), so both are added back in.

Sources, by era; each session counts once however many files repeat it, and in the run that recorded it
first (see `run_tokens`):
- `agent_events.jsonl` `usage` events (agent-event-v1, harnesses/ since Oct 2026), one per turn, in the
  run folder and nested sessions (Harness² rollouts and coach sessions, AVO optimizer and research).
  `turns.jsonl` repeats them and is not read.
- OpenCode sessions of that era count their `raw/turn-N.jsonl` `step_finish` parts instead of the usage
  events: a turn that was stopped or timed out has parts but no usage event.
- Codex app-server `thread/tokenUsage/updated` events (AVO Aug-Sep 2026, in `agent_events.jsonl`, else
  `app_server_events.jsonl`): a running total per thread, so the largest per thread counts.
- `codex_session.jsonl` (Codex direct player, Sep 2026): a running `turn.usage.total`; a drop starts a new thread.
- OpenCode server `step-finish` parts (OpenCode AVO, Sep 2026). Parts are deduplicated by id.
- `model_session.jsonl` (raw OpenRouter player, Oct 2026): one OpenRouter `usage` per reply.
Runs with compact Codex tracing (AVO Sep 14-24 2026) or only request captures recorded no usage: None.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

SOURCES = ("agent_events.jsonl", "app_server_events.jsonl", "codex_session.jsonl", "model_session.jsonl")
# Agent scratch space, frames and request captures hold no usage and dominate the file count.
PRUNE = {"frames", "initial_frames", "model_requests", "workspace_blobs", "world_model_snapshots", "node_modules"}
MARKERS = (b'"usage"', b"tokenUsage", b"step-finish", b"step_finish")
KEYS = ("input", "output", "reasoning", "cached")

INDEX_SECONDS = 30

_cache: dict[str, tuple[tuple, dict, dict]] = {}
_index_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()


def _number(value) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else 0


def _record(input=0, output=0, reasoning=0, cached=0) -> dict:
    return dict(zip(KEYS, map(_number, (input, output, reasoning, cached))))


def _sources(run_dir: Path) -> list[os.DirEntry]:
    found, stack = [], [str(run_dir)]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as listing:
                entries = list(listing)
        except OSError:
            continue
        names = {entry.name for entry in entries}
        raw = os.path.basename(directory) == "raw"
        for entry in entries:
            try:
                if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in PRUNE and "workspace" not in entry.name and not entry.name.startswith("."):
                        stack.append(entry.path)
                # The full app-server log repeats the compact log's usage events (and is several times larger).
                elif entry.name == "app_server_events.jsonl" and "agent_events.jsonl" in names:
                    continue
                elif entry.name in SOURCES or (raw and entry.name.startswith("turn-") and entry.name.endswith(".jsonl")):
                    found.append(entry)
            except OSError:
                continue
    return found


def _opencode(tokens: dict) -> dict:
    cache = tokens.get("cache") or {}
    return _record(_number(tokens.get("input")) + _number(cache.get("read")) + _number(cache.get("write")),
                   _number(tokens.get("output")) + _number(tokens.get("reasoning")),
                   tokens.get("reasoning"), cache.get("read"))


def _keep_largest(running: dict, key: tuple, record: dict) -> None:
    best = running.get(key)
    if best is None or record["input"] + record["output"] > best["input"] + best["output"]:
        running[key] = record


def _read(path: str, counted: dict, running: dict) -> None:
    """Add one file's sessions: per-call usage to `counted`, running totals to `running` (largest kept)."""
    raw = os.path.basename(os.path.dirname(path)) == "raw"
    previous = segment = None
    try:
        with open(path, "rb") as stream:
            for number, line in enumerate(stream):
                if not any(marker in line for marker in MARKERS):
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                usage = event.get("usage")
                turn = event.get("turn")
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                if raw:  # only OpenCode's steps: other CLIs' raw streams repeat their usage events
                    part = event.get("part") or {}
                    if event.get("type") == "step_finish" and isinstance(part.get("tokens"), dict):
                        counted[("part", part.get("id") or (path, number))] = _opencode(part["tokens"])
                elif event.get("schema") == "agent-event-v1":
                    if event.get("type") == "usage" and isinstance(usage, dict) and event.get("harness") not in ("opencode", "opencode-lean"):
                        key = ("event", event.get("session"), event.get("role"), turn, event.get("t"))
                        counted[key] = _record(*(usage.get(name) for name in KEYS))
                elif event.get("method") == "thread/tokenUsage/updated":
                    total = (payload.get("tokenUsage") or {}).get("total") or {}
                    record = _record(total.get("inputTokens"), total.get("outputTokens"),
                                     total.get("reasoningOutputTokens"), total.get("cachedInputTokens"))
                    _keep_largest(running, ("thread", payload.get("threadId") or path), record)
                elif event.get("method") == "message.part.updated":
                    part = payload.get("part") or {}
                    if part.get("type") == "step-finish" and isinstance(part.get("tokens"), dict):
                        counted[("part", part.get("id") or (path, number))] = _opencode(part["tokens"])
                elif isinstance(turn, dict) and isinstance(turn.get("usage"), dict):
                    total = turn["usage"].get("total") or {}
                    record = _record(total.get("inputTokens"), total.get("outputTokens"),
                                     total.get("reasoningOutputTokens"), total.get("cachedInputTokens"))
                    if previous is None or record["input"] + record["output"] < previous:
                        segment = ("codex-session", turn.get("id") or (path, number))  # named by its first turn
                    previous = record["input"] + record["output"]
                    _keep_largest(running, segment, record)
                elif isinstance(usage, dict) and "prompt_tokens" in usage:
                    record = _record(usage.get("prompt_tokens"), usage.get("completion_tokens"),
                                     (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                                     (usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
                    reply = (event.get("timestamp"), event.get("sequence"), turn)
                    counted[("reply", *(reply if any(reply) else (path, number)))] = record
    except OSError:
        pass


def _sessions(run_dir: Path) -> tuple[tuple, dict, dict]:
    """(stamp, counted, running) for one run folder, cached until a source file changes."""
    files = _sources(Path(run_dir))
    stamps = []
    for entry in files:
        try:
            stamps.append(entry.stat().st_mtime)
        except OSError:
            pass
    stamp = (max(stamps, default=0), len(files))
    key = str(run_dir)
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            return cached
    counted, running = {}, {}
    for entry in files:
        _read(entry.path, counted, running)
    with _lock:
        _cache[key] = (stamp, counted, running)
    return stamp, counted, running


def _index(runs: tuple[str, ...]) -> dict:
    """Session key -> [(order, usage)] over `runs`; rebuilt at most every INDEX_SECONDS."""
    with _lock:
        cached = _index_cache.get(runs)
        if cached and time.monotonic() - cached[0] < INDEX_SECONDS:
            return cached[1]
    index: dict = {}
    for run in runs:
        stamp, counted, running = _sessions(Path(run))
        for name, record in [*counted.items(), *running.items()]:
            index.setdefault(name, []).append(((stamp[0], run), record))
    with _lock:
        _index_cache.clear()  # one catalog at a time
        _index_cache[runs] = (time.monotonic(), index)
    return index


def run_tokens(run_dir: Path, runs=()) -> dict | None:
    """{"input", "output", "reasoning", "cached", "total"} over the run's sessions, or None if none recorded usage.

    `runs` are the catalog's other run folders. A continued run starts from a copy of its source's folder
    (no pointer to it is recorded), so a session also recorded by a run whose files are older belongs to that
    run: a copied call is not counted again, and a copied running total counts only what it grew by here.
    """
    stamp, counted, running = _sessions(run_dir)
    index = _index(tuple(sorted({str(r) for r in runs} | {str(run_dir)}))) if runs else {}
    order = (stamp[0], str(run_dir))

    def inherited(name: tuple) -> list[dict]:
        return [record for other, record in index.get(name, ()) if other < order]

    records = [record for name, record in counted.items() if not inherited(name)]
    for name, record in running.items():
        before = max(inherited(name), key=lambda r: r["input"] + r["output"], default=None)
        records.append(record if before is None else {k: max(0, record[k] - before[k]) for k in KEYS})
    if not counted and not running:
        return None
    result = {key: sum(r[key] for r in records) for key in KEYS}
    result["total"] = result["input"] + result["output"]
    return result
