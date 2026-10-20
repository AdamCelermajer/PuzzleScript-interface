"""Model-facing projection of trusted records; original artifacts are untouched."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from frameworks.avo.isolation import IsolationError


_PRIVATE_KEYS = {
    "game_id", "game_name", "game_title", "source_name", "source_url", "legend",
    "profile_settings", "profile_manifest", "profile_prompt", "base_prompt",
    "run_config", "session_manifest", "analysis", "output_dir", "run_dir",
    "transcript", "history_path",
}
_OBSERVATION_KEYS = {"payload", "status", "progress", "available_actions", "metadata"}
_FRAME_KEYS = {"mime_type", "width", "height", "sha256"}


class ModelView:
    def __init__(self, workspace: Path, artifact_roots: tuple[Path, ...]) -> None:
        self.workspace = workspace.resolve()
        self.artifact_roots = tuple(path.resolve() for path in artifact_roots)

    def _frame(self, value: dict) -> dict:
        raw = value.get("path")
        if not raw:
            raise IsolationError("Rendered frame has no artifact path")
        original = Path(raw)
        # Check every component: a regular file reached through a junction is
        # still an escape, even when the final file itself is not a symlink.
        if any(part.is_symlink() or part.is_junction() for part in (original, *original.parents)):
            raise IsolationError("Rendered frame path contains a link")
        path = original.resolve()
        if not any(path.is_relative_to(root) for root in (*self.artifact_roots, self.workspace)):
            raise IsolationError("Rendered frame is outside the permitted artifact roots")
        # Reject links before dereferencing and stage byte-identical PNGs only.
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise IsolationError("Rendered frame is not PNG")
        digest = hashlib.sha256(data).hexdigest()
        target = self.workspace / "observations" / f"{digest}.png"
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        result = {key: value[key] for key in _FRAME_KEYS if key in value}
        result.update(path=str(target), sha256=digest)
        return result

    def present(self, value: Any, *, key: str = "") -> Any:
        if isinstance(value, list) or isinstance(value, tuple):
            return [self.present(item) for item in value]
        if not isinstance(value, dict):
            return value
        if key == "rendered_frame":
            return self._frame(value)
        if "payload" in value and "status" in value and "available_actions" in value:
            value = {name: item for name, item in value.items() if name in _OBSERVATION_KEYS}
        result = {}
        for name, item in value.items():
            if name in _PRIVATE_KEYS:
                continue
            if name in {"solver_evaluation", "solver", "research", "evaluation"} and isinstance(item, str):
                continue
            if name in {"path", "draft_path", "artifact_path"}:
                # Candidate archive paths have no model-visible role. Local
                # editable drafts are the exception and use relative paths.
                path = Path(str(item)).resolve()
                if path.is_relative_to(self.workspace):
                    result[name] = path.relative_to(self.workspace).as_posix()
                continue
            if name == "metadata" and isinstance(item, dict):
                item = {k: v for k, v in item.items() if k in {"projection", "rendered_frame"}}
            result[name] = self.present(item, key=name)
        return result

    def error(self, exc: Exception) -> str:
        # Detailed exceptions belong in trusted logs, not the agent's context.
        message = str(exc)
        if any(str(root).lower() in message.lower() for root in self.artifact_roots) or ":\\" in message or ":/" in message:
            return f"{type(exc).__name__}: operation failed; internal path withheld"
        if isinstance(exc, OSError):
            return f"{type(exc).__name__}: file operation failed"
        return f"{type(exc).__name__}: {message}"
