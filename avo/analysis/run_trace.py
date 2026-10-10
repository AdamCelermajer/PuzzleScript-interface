from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4


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
    """Record a complete Codex app-server session outside its workspace.

    ``agent_events.jsonl`` remains the small, reasoning-redacted compatibility
    trace. ``app_server_events.jsonl`` is the authoritative unfiltered stream.
    """

    root: Path
    workspace: Path

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.workspace = self.workspace.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.full_trace = os.environ.get("AVO_TRACE_DETAIL", "full") == "full"
        self.blob_root = self.root / "workspace_blobs"
        self.blob_root.mkdir(exist_ok=True)
        self.events_path = self.root / "agent_events.jsonl"
        self.raw_events_path = self.root / "app_server_events.jsonl"
        self.conversation_path = self.root / "conversation.jsonl"
        self.turn_inputs_path = self.root / "turn_inputs.jsonl"
        self.prompt_path = self.root / "prompt.json"
        self.session_path = self.root / "session.json"
        self.changes_path = self.root / "workspace_changes.jsonl"
        self.transport_root = self.root / "model_requests"
        self._workspace_manifest: dict[str, dict[str, Any]] = {}
        self._session: dict[str, Any] = {}

    def start_session(
        self,
        *,
        role: str,
        model: str,
        effort: str,
        codex_bin: str,
        base_instructions: str,
        ephemeral: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        started_at = _now()
        session_id = str(uuid4())
        self._write_json(
            self.prompt_path,
            {
                "schema_version": 1,
                "session_id": session_id,
                "recorded_at": started_at,
                "base_instructions": base_instructions,
                "sha256": hashlib.sha256(base_instructions.encode("utf-8")).hexdigest(),
            },
        )
        self._session = {
            "schema_version": 1,
            "session_id": session_id,
            "status": "running",
            "started_at": started_at,
            "ended_at": None,
            "role": role,
            "thread_id": None,
            "model": model,
            "effort": effort,
            "codex_bin": codex_bin,
            "cwd": str(self.workspace),
            "ephemeral": ephemeral,
            "metadata": _jsonable(metadata or {}),
            "capture": {
                "app_server_events": "complete unfiltered SDK notification stream" if self.full_trace else "disabled (compact tracing)",
                "workspace_snapshots": self.full_trace,
                "model_requests_requested": True,
                "model_request_files": 0,
                "model_request_status": "pending",
            },
            "artifacts": {
                "prompt": self.prompt_path.name,
                "turn_inputs": self.turn_inputs_path.name,
                "app_server_events": self.raw_events_path.name,
                "conversation": self.conversation_path.name,
                "compact_events": self.events_path.name,
                "workspace_changes": self.changes_path.name,
                "workspace_blobs": self.blob_root.name,
                "model_requests": self.transport_root.name,
            },
        }
        self._write_json(self.session_path, self._session)

    def attach_thread(self, thread_id: str | None) -> None:
        if self._session:
            self._session["thread_id"] = thread_id
            self._write_json(self.session_path, self._session)

    @property
    def session_id(self) -> str | None:
        return str(self._session.get("session_id")) if self._session else None

    def record_turn_input(
        self,
        *,
        turn_number: int,
        turn_id: str | None,
        instruction: str,
        effort: str,
    ) -> None:
        recorded_at = _now()
        payload = {
            "recorded_at": recorded_at,
            "session_id": self.session_id,
            "turn": turn_number,
            "turn_id": turn_id,
            "effort": effort,
            "inputs": [{"type": "text", "text": instruction}],
        }
        self._append(self.turn_inputs_path, payload)
        self._append(
            self.conversation_path,
            {
                "recorded_at": recorded_at,
                "session_id": self.session_id,
                "turn": turn_number,
                "turn_id": turn_id,
                "source": "client_turn_input",
                "type": "userMessage",
                "role": "user",
                "content": instruction,
            },
        )

    def record_event(
        self,
        event: Any,
        turn_number: int,
        turn_id: str | None = None,
    ) -> None:
        method = str(getattr(event, "method", "unknown"))
        payload = _jsonable(getattr(event, "payload", None))
        envelope = {
            "recorded_at": _now(),
            "session_id": self.session_id,
            "turn": turn_number,
            "turn_id": turn_id,
            "method": method,
            "payload": payload,
        }
        if self.full_trace:
            self._append(self.raw_events_path, envelope)
        self._record_conversation_item(envelope)

        if self.full_trace and "reasoning" not in method.lower() and not method.lower().endswith("delta"):
            compact_payload = payload
            if method in {"item/started", "item/completed"}:
                compact_payload = self._without_reasoning_item(payload)
            self._append(self.events_path, {**envelope, "payload": compact_payload})
        if method in {"item/completed", "turn/completed"}:
            self.snapshot(f"turn:{turn_number}:{method}")

    def record_conversation(self, record: dict[str, Any]) -> None:
        """Append one harness-produced item in the app-server conversation shape."""
        self._append(self.conversation_path, record)

    def traced(
        self,
        events: Iterator[Any],
        turn_number: int,
        turn_id: str | None = None,
    ) -> Iterator[Any]:
        for event in events:
            self.record_event(event, turn_number, turn_id)
            yield event

    def finish_session(self, *, status: str, error: str | None = None) -> None:
        if not self._session:
            return
        request_files = (
            len(list(self.transport_root.glob("request-*.json")))
            if self.transport_root.is_dir()
            else 0
        )
        capture = self._session["capture"]
        capture["model_request_files"] = request_files
        capture["model_request_status"] = (
            "captured" if request_files else "unsupported_or_no_requests"
        )
        self._session["status"] = status
        self._session["ended_at"] = _now()
        if error:
            self._session["error"] = error
        self._write_json(self.session_path, self._session)

    def snapshot(self, cause: str) -> None:
        if not self.full_trace:
            return
        current: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, str]] = []
        for path in sorted(self.workspace.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.workspace)
            if any(part in {".avo_rpc", ".avo_evolution_rpc", ".tmp", "__pycache__"} for part in relative.parts):
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

        added = {
            name: data for name, data in current.items() if name not in self._workspace_manifest
        }
        modified = {
            name: data
            for name, data in current.items()
            if name in self._workspace_manifest
            and data["sha256"] != self._workspace_manifest[name]["sha256"]
        }
        deleted = sorted(name for name in self._workspace_manifest if name not in current)
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
        self._workspace_manifest = current

    def _record_conversation_item(self, envelope: dict[str, Any]) -> None:
        if envelope["method"] != "item/completed":
            return
        payload = envelope["payload"]
        if not isinstance(payload, dict) or not isinstance(payload.get("item"), dict):
            return
        item = payload["item"]
        item_type = str(item.get("type", "unknown"))
        role = {
            "userMessage": "user",
            "agentMessage": "assistant",
            "reasoning": "assistant_reasoning",
        }.get(item_type, "tool")
        self._append(
            self.conversation_path,
            {
                "recorded_at": envelope["recorded_at"],
                "turn": envelope["turn"],
                "turn_id": envelope["turn_id"],
                "source": "app_server_item_completed",
                "type": item_type,
                "role": role,
                "item": item,
            },
        )

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

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
