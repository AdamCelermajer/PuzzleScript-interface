"""Draft vocabulary tags and a one-line summary per game with the Claude Code CLI.

Each game is one headless ``claude -p`` call with structured output, no tools, an
empty temporary config directory and an empty temporary working directory. The
script text goes in the prompt via stdin. Results are written to
``benchmark/games.json`` after every game (resumable). ``reviewed`` tags are
never touched; already drafted games are skipped unless ``--force``.

    uv run python -m scripts.draft_game_tags [--games ID ...] [--force] [--concurrency 4]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from scripts.build_game_metadata import (DERIVED_PROPERTIES, GAMES_JSON, ROOT, TAG_VOCABULARY,
                                         read_json, write_json_atomic)

MODEL = "claude-sonnet-5-5"
MAX_SCRIPT_CHARS = 120_000
WEB_TOOLS = ["WebSearch", "WebFetch", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "Task", "Agent"]
LLM_PROPERTIES = [p for p in TAG_VOCABULARY["properties"] if p not in DERIVED_PROPERTIES]
SCHEMA = {
    "type": "object",
    "properties": {
        "mechanics": {"type": "array", "items": {"type": "string", "enum": list(TAG_VOCABULARY["mechanics"])}},
        "properties": {"type": "array", "items": {"type": "string", "enum": LLM_PROPERTIES}},
        "summary": {"type": "string"},
    },
    "required": ["mechanics", "properties", "summary"],
    "additionalProperties": False,
}


def env_token(root: Path) -> str:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    env_file = root / ".env"
    if not token and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "CLAUDE_CODE_OAUTH_TOKEN":
                token = value.strip().strip('"').strip("'")
    if not token:
        raise SystemExit("CLAUDE_CODE_OAUTH_TOKEN is not set in the environment or .env")
    return token


def prompt(game_id: str, entry: dict, script: str) -> str:
    def block(kind):
        return "\n".join(f"- {term}: {text}" for term, text in TAG_VOCABULARY[kind].items()
                         if kind == "mechanics" or term in LLM_PROPERTIES)
    if len(script) > MAX_SCRIPT_CHARS:
        script = script[:MAX_SCRIPT_CHARS] + "\n[... truncated ...]"
    return f"""You are cataloguing PuzzleScript games for a research benchmark. Read the game source below
and classify it using ONLY the controlled vocabulary.

Mechanics (choose every one that matters for solving the levels, usually 2-6):
{block("mechanics")}

Properties (choose only clear cases; may be empty):
{block("properties")}

Rules:
- Tag what the RULES, WINCONDITIONS and LEVELS actually do, not what sprite names suggest.
- Ignore purely cosmetic rules (animations, wall-edge decoration, left/right facing sprites, sound).
- summary: one plain sentence (at most 160 characters) describing the core mechanic and goal,
  without level-by-level solutions.

Game: {entry.get("title") or game_id} ({game_id}), {entry.get("levels")} playable levels.

=== SCRIPT START ===
{script}
=== SCRIPT END ===
"""


def draft_one(game_id: str, entry: dict, script: str, token: str, timeout: int) -> dict:
    temp = Path(tempfile.mkdtemp(prefix="draft-tags-"))
    try:
        (temp / "config").mkdir()
        (temp / "cwd").mkdir()
        env = {k: v for k, v in os.environ.items() if k not in {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"}}
        env.update(CLAUDE_CODE_OAUTH_TOKEN=token, CLAUDE_CONFIG_DIR=str(temp / "config"))
        command = [shutil.which("claude") or "claude", "-p", "--output-format", "json", "--model", MODEL,
                   "--json-schema", json.dumps(SCHEMA), "--tools", "", "--disallowedTools", *WEB_TOOLS,
                   "--strict-mcp-config", "--no-session-persistence"]
        result = subprocess.run(command, input=prompt(game_id, entry, script), capture_output=True,
                                text=True, encoding="utf-8", cwd=temp / "cwd", env=env, timeout=timeout)
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            raise RuntimeError(f"exit {result.returncode}: {(result.stderr or result.stdout)[-400:]}")
        output = payload.get("structured_output")
        if payload.get("is_error") or not isinstance(output, dict):
            raise RuntimeError(f"no structured output: {str(payload.get('result'))[:400]}")
        mechanics = [t for t in TAG_VOCABULARY["mechanics"] if t in set(output.get("mechanics") or [])]
        properties = [t for t in LLM_PROPERTIES if t in set(output.get("properties") or [])]
        summary = " ".join(str(output.get("summary") or "").split())
        if not summary:
            raise RuntimeError("empty summary")
        return {"mechanics": mechanics, "properties": properties, "summary": summary}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--games", nargs="*", help="only these game ids")
    parser.add_argument("--force", action="store_true", help="redraft games already drafted")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-failure-rate", type=float, default=0.10)
    args = parser.parse_args(argv)

    path = args.root / GAMES_JSON
    data = read_json(path)
    if not data:
        raise SystemExit(f"{path} is missing; run scripts.build_game_metadata first")
    token = env_token(args.root)
    games_dir = args.root / "puzzlescript_interface/games"
    todo = []
    for game_id, entry in data["games"].items():
        if args.games and game_id not in args.games:
            continue
        if entry.get("tags_status") == "reviewed" or not (games_dir / game_id / "script.txt").is_file():
            continue
        if entry.get("tags_status") == "draft" and not args.force:
            continue
        todo.append(game_id)
    print(f"drafting {len(todo)} games with {MODEL}", flush=True)

    lock = threading.Lock()
    failures: list[tuple[str, str]] = []
    done = 0
    stop = threading.Event()

    def save(game_id: str, draft: dict) -> None:
        with lock:  # re-read so concurrent API edits made meanwhile are kept
            current = read_json(path)
            entry = current["games"][game_id]
            if entry.get("tags_status") == "reviewed":
                return
            derived = [p for p in entry.get("tags", {}).get("properties", []) if p in DERIVED_PROPERTIES]
            entry["tags"] = {"mechanics": draft["mechanics"], "properties": draft["properties"] + derived}
            entry["tags_status"] = "draft"
            entry["tags_model"] = MODEL
            entry["tags_drafted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if not entry.get("summary") or entry.get("summary_source") == "draft":
                entry["summary"], entry["summary_source"] = draft["summary"], "draft"
            write_json_atomic(path, current)

    def work(game_id: str):
        if stop.is_set():
            return game_id, None, "skipped after failure limit"
        script = (games_dir / game_id / "script.txt").read_text(encoding="utf-8", errors="replace")
        last = ""
        for attempt in range(2):
            try:
                return game_id, draft_one(game_id, data["games"][game_id], script, token, args.timeout), None
            except (RuntimeError, subprocess.SubprocessError, OSError) as error:
                last = str(error)
                time.sleep(3 * (attempt + 1))
        return game_id, None, last

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [pool.submit(work, game_id) for game_id in todo]
        for future in as_completed(futures):
            game_id, draft, error = future.result()
            done += 1
            if draft:
                save(game_id, draft)
                print(f"[{done}/{len(todo)}] {game_id}: {', '.join(draft['mechanics'])} | {draft['summary']}", flush=True)
            elif error != "skipped after failure limit":
                failures.append((game_id, error))
                print(f"[{done}/{len(todo)}] {game_id}: FAILED {error}", flush=True)
                if len(failures) > max(3, args.max_failure_rate * len(todo)):
                    stop.set()
    if failures:
        print(f"{len(failures)} failures:", *(f"  {g}: {e}" for g, e in failures), sep="\n")
    if stop.is_set():
        print("stopped: failure rate above limit")
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
