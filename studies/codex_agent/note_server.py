from __future__ import annotations

import argparse
import difflib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


NOTE_EXTENSIONS = {".md", ".txt"}
MAX_NOTE_CHARACTERS = 65_536

TOOLS = [
    {
        "name": "list_notes",
        "description": "List the note files currently saved in the persistent workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "read_note",
        "description": "Read one saved note file from the persistent workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_note",
        "description": (
            "Create or replace one .md or .txt note in the persistent workspace so "
            "observations and strategy can be remembered across game turns."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
]


class NoteWorkspace:
    def __init__(self, root: str | Path, history_root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_root = Path(history_root).resolve()
        self.history_root.mkdir(parents=True, exist_ok=True)
        if self.history_root == self.root or self.root in self.history_root.parents:
            raise ValueError("Note history must be outside the model workspace")
        self.audit_path = self.root / "tool_calls.jsonl"

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        audit_extra: dict[str, Any] = {}
        if name == "list_notes":
            files = sorted(
                path.relative_to(self.root).as_posix()
                for path in self.root.rglob("*")
                if path.is_file() and path.suffix.lower() in NOTE_EXTENSIONS
            )
            result: dict[str, Any] = {"files": files}
        elif name == "read_note":
            target = self._note_path(str(arguments.get("path", "")))
            result = {
                "path": target.relative_to(self.root).as_posix(),
                "content": target.read_text(encoding="utf-8"),
            }
        elif name == "write_note":
            target = self._note_path(str(arguments.get("path", "")))
            content = str(arguments.get("content", ""))
            if len(content) > MAX_NOTE_CHARACTERS:
                raise ValueError(
                    f"Note content exceeds {MAX_NOTE_CHARACTERS} characters"
                )
            previous_content = (
                target.read_text(encoding="utf-8") if target.exists() else None
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            history_path, version = self._snapshot(target, content)
            self._record_write_transition(
                target=target,
                previous_content=previous_content,
                content=content,
                history_path=history_path,
                version=version,
            )
            result = {
                "path": target.relative_to(self.root).as_posix(),
                "characters": len(content),
            }
            audit_extra = {"version": version, "history_path": history_path}
        else:
            raise ValueError(f"Unknown note tool: {name}")
        self._record(name, arguments, result, audit_extra)
        return result

    def _note_path(self, raw_path: str) -> Path:
        relative = Path(raw_path.strip())
        if not raw_path.strip() or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Note path must stay inside the workspace")
        if relative.suffix.lower() not in NOTE_EXTENSIONS:
            raise ValueError("Note path must end in .md or .txt")
        target = (self.root / relative).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Note path escapes the workspace")
        return target

    def _snapshot(self, target: Path, content: str) -> tuple[str, int]:
        relative = target.relative_to(self.root)
        version_dir = self.history_root / relative.parent / f"{relative.name}.versions"
        version_dir.mkdir(parents=True, exist_ok=True)
        versions = [
            int(path.stem)
            for path in version_dir.glob(f"*{relative.suffix.lower()}")
            if path.stem.isdigit()
        ]
        version = max(versions, default=0) + 1
        snapshot = version_dir / f"{version:06d}{relative.suffix.lower()}"
        snapshot.write_text(content, encoding="utf-8")
        return snapshot.relative_to(self.history_root).as_posix(), version

    def _record_write_transition(
        self,
        *,
        target: Path,
        previous_content: str | None,
        content: str,
        history_path: str,
        version: int,
    ) -> None:
        relative = target.relative_to(self.root).as_posix()
        before_lines = (previous_content or "").splitlines(keepends=True)
        after_lines = content.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"{relative}@{version - 1:06d}",
                tofile=f"{relative}@{version:06d}",
            )
        )
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "path": relative,
            "before_version": version - 1 if previous_content is not None else None,
            "after_version": version,
            "history_path": history_path,
            "changed": previous_content != content,
            "before_content": previous_content,
            "after_content": content,
            "unified_diff": diff,
        }
        transition_path = self.history_root / "note_transitions.jsonl"
        with transition_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def _record(
        self,
        name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        extra: dict[str, Any],
    ) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tool": name,
            "path": str(arguments.get("path", "")),
            "characters": result.get("characters"),
            "version": extra.get("version"),
            "history_path": extra.get("history_path"),
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "structuredContent": payload,
        "isError": False,
    }


def serve(workspace: NoteWorkspace) -> None:
    for raw_line in sys.stdin:
        request: dict[str, Any] = {}
        try:
            request = json.loads(raw_line)
            request_id = request.get("id")
            method = request.get("method")
            if method == "initialize":
                requested_version = request.get("params", {}).get(
                    "protocolVersion", "2025-06-18"
                )
                result = {
                    "protocolVersion": requested_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "codex-notes", "version": "1.0.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    payload = workspace.call(
                        str(params.get("name", "")),
                        dict(params.get("arguments", {})),
                    )
                    result = _tool_result(payload)
                except (OSError, ValueError) as exc:
                    result = {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    }
            else:
                if request_id is None:
                    continue
                raise ValueError(f"Unsupported MCP method: {method}")
            if request_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--history-dir", required=True)
    args = parser.parse_args()
    serve(NoteWorkspace(args.workspace, args.history_dir))


if __name__ == "__main__":
    main()
