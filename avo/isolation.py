"""Workspace helpers for AVO runs. Isolation itself is the Docker container (see harnesses/README.md)."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

ISOLATION_VERSION = 2  # 1 = Codex sandbox + request proxy; 2 = one plain Docker container per run
REPOSITORY = Path(__file__).resolve().parents[1]


class IsolationError(RuntimeError):
    """Infrastructure failure, not a solver score or an experimental outcome."""


def runtime_root() -> Path:
    """Scratch root for agent workspaces, outside the repository."""
    root = Path(os.environ.get("AVO_WORKSPACE_ROOT") or Path.home() / ".avo" / "workspaces").resolve()
    if root == REPOSITORY or REPOSITORY in root.parents:
        raise IsolationError("AVO workspace root must be outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_workspace(prefix: str = "w-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix, dir=runtime_root())).resolve()


def cleanup_private_directory(path: Path) -> None:
    """Remove one finished workspace created by ``new_workspace``."""
    path = Path(path)
    if path.is_symlink() or path.resolve().parent != runtime_root() or not path.name.startswith(("w-", "s-")):
        raise IsolationError("Cleanup target is not an owned workspace directory")
    shutil.rmtree(path, ignore_errors=True)
