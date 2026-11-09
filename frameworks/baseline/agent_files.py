"""Every file in the player's folder, version by version, whoever wrote it (a write tool, an edit, a
shell command): after every move the folder is compared with the last look, and each added, changed
or deleted file is recorded in the run folder's ``agent_files/``.

``agent_files/index.jsonl`` holds one line per change: ``{at, label, t, path, status, size, file}``,
where ``at`` orders the looks (moves for the agentic driver, turns for the turn-based one), ``status``
is ``added``, ``changed`` or ``deleted``, and ``file`` is the saved copy (``<at>/<path>``, none for a
deletion). The run page's Agent files tab reads it (workbench/record_routes.py).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

FOLDER = "agent_files"
# Written by the controller, not the player: the current picture.
OURS = {"frame.png"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git"}
MAX_BYTES = 2_000_000  # a larger file is listed with its size but not copied


class FileHistory:
    def __init__(self, folder: Path, output: Path):
        self.folder, self.root = Path(folder), Path(output) / FOLDER
        self.seen: dict[str, str] = {}  # path -> content hash at the last look

    def _files(self) -> dict[str, Path]:
        found = {}
        for path in sorted(self.folder.rglob("*")):
            relative = path.relative_to(self.folder)
            if (path.is_file() and not path.is_symlink() and relative.as_posix() not in OURS
                    and not SKIP_DIRS.intersection(relative.parts)):
                found[relative.as_posix()] = path
        return found

    def capture(self, at: int, label: str) -> None:
        """Record what changed in the folder since the last look; ``label`` says when (e.g. "after 12 moves")."""
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = []
        files = self._files()
        for name, path in files.items():
            try:
                data = path.read_bytes()
            except OSError:
                continue
            digest = hashlib.sha256(data).hexdigest()
            if self.seen.get(name) == digest:
                continue
            status = "changed" if name in self.seen else "added"
            self.seen[name] = digest
            copy = None
            if len(data) <= MAX_BYTES:
                copy = f"{at:05d}/{name}"
                target = self.root / copy
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            lines.append({"at": at, "label": label, "t": stamp, "path": name, "status": status, "size": len(data),
                          "file": copy})
        for name in sorted(set(self.seen) - set(files)):
            del self.seen[name]
            lines.append({"at": at, "label": label, "t": stamp, "path": name, "status": "deleted", "size": 0,
                          "file": None})
        if lines:
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / "index.jsonl").open("a", encoding="utf-8") as stream:
                stream.writelines(json.dumps(line) + "\n" for line in lines)
