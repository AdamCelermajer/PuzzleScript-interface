from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunTraceRecorder:
    """Observe a Codex run without placing analysis state in its workspace."""

    root: Path
    workspace: Path

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.workspace = self.workspace.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.blob_root = self.root / "workspace_blobs"
        self.blob_root.mkdir(exist_ok=True)
        self.events_path = self.root / "agent_events.jsonl"
        self.changes_path = self.root / "workspace_changes.jsonl"
        self._manifest: dict[str, dict[str, Any]] = {}

    def record_event(self, event: Any, turn_number: int) -> None:
        method = str(getattr(event, "method", "unknown"))
        if "reasoning" in method.lower() or method.lower().endswith("delta"):
            return
        payload = _jsonable(getattr(event, "payload", None))
        if method in {"item/started", "item/completed"}:
            payload = self._without_reasoning_item(payload)
        self._append(
            self.events_path,
            {
                "recorded_at": _now(),
                "turn": turn_number,
                "method": method,
                "payload": payload,
            },
        )
        if method in {"item/completed", "turn/completed"}:
            self.snapshot(f"turn:{turn_number}:{method}")

    def traced(self, events: Iterator[Any], turn_number: int) -> Iterator[Any]:
        for event in events:
            self.record_event(event, turn_number)
            yield event

    def snapshot(self, cause: str) -> None:
        current: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, str]] = []
        for path in sorted(self.workspace.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.workspace)
            if ".avo_rpc" in relative.parts or "__pycache__" in relative.parts:
                continue
            try:
                content = path.read_bytes()
            except OSError as exc:
                errors.append(
                    {"path": relative.as_posix(), "error": f"{type(exc).__name__}: {exc}"}
                )
                continue
            digest = hashlib.sha256(content).hexdigest()
            name = relative.as_posix()
            current[name] = {"sha256": digest, "size": len(content)}
            blob = self.blob_root / digest
            if not blob.exists():
                try:
                    blob.write_bytes(content)
                except OSError as exc:
                    errors.append(
                        {"path": name, "error": f"{type(exc).__name__}: {exc}"}
                    )

        added = {name: data for name, data in current.items() if name not in self._manifest}
        modified = {
            name: data
            for name, data in current.items()
            if name in self._manifest and data["sha256"] != self._manifest[name]["sha256"]
        }
        deleted = sorted(name for name in self._manifest if name not in current)
        if added or modified or deleted or errors:
            self._append(
                self.changes_path,
                {
                    "recorded_at": _now(),
                    "cause": cause,
                    "added": added,
                    "modified": modified,
                    "deleted": deleted,
                    "errors": errors,
                },
            )
        self._manifest = current

    @staticmethod
    def _without_reasoning_item(payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        item = payload.get("item")
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            return payload
        sanitized = dict(payload)
        sanitized["item"] = {
            "id": item.get("id"),
            "type": "reasoning",
            "content": "[not recorded]",
        }
        return sanitized

    @staticmethod
    def _append(path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
