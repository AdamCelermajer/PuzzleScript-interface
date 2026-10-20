"""Pinned moments of runs (a reasoning step, a message, a tool call), kept apart from run outputs.

A pin copies the event's text, so it stays readable when the run's event window or files change.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from uuid import uuid4

from workbench.catalog import read_json, run_path

PINS = "output/workbench/pins.json"
TEXT_LIMIT = 20_000
_lock = threading.Lock()


def read_pins(root: Path, run: str | None = None) -> list[dict]:
    pins = read_json(root / PINS).get("pins")
    pins = [p for p in pins if isinstance(p, dict)] if isinstance(pins, list) else []
    return [p for p in pins if run is None or p.get("run") == run]


def _write(root: Path, pins: list[dict]) -> None:
    path = root / PINS
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"pins": pins}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _text(value, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Pin fields must be text")
    return value[:limit]


def add_pin(root: Path, payload: dict) -> dict:
    run = payload.get("run")
    if not isinstance(run, str) or not run:
        raise ValueError("A pin needs the run id")
    run_path(run, root)  # rejects ids outside the repository
    turn = payload.get("turn")
    if turn is not None and (not isinstance(turn, int) or isinstance(turn, bool)):
        raise ValueError("turn must be an integer or null")
    pin = {"id": uuid4().hex[:12], "run": run, "key": _text(payload.get("key"), 400),
           "context": _text(payload.get("context"), 200), "turn": turn,
           "kind": _text(payload.get("kind"), 40), "title": _text(payload.get("title"), 200),
           "text": _text(payload.get("text"), TEXT_LIMIT), "at": _text(payload.get("at"), 40) or None,
           "note": _text(payload.get("note"), 4000), "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if not pin["text"]:
        raise ValueError("A pin needs the text it keeps")
    with _lock:
        pins = read_pins(root)
        same = next((p for p in pins if pin["key"] and p.get("run") == run and p.get("key") == pin["key"]), None)
        if same:
            return same
        _write(root, [*pins, pin])
    return pin


def update_pin(root: Path, pin_id: str, note) -> dict:
    with _lock:
        pins = read_pins(root)
        pin = next((p for p in pins if p.get("id") == pin_id), None)
        if pin is None:
            raise KeyError(pin_id)
        pin["note"] = _text(note, 4000)
        _write(root, pins)
    return pin


def remove_pin(root: Path, pin_id: str) -> None:
    with _lock:
        pins = read_pins(root)
        kept = [p for p in pins if p.get("id") != pin_id]
        if len(kept) == len(pins):
            raise KeyError(pin_id)
        _write(root, kept)
