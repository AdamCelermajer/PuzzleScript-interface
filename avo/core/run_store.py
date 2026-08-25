from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunStore:
    """Generic on-disk layout for one AVO run."""

    root: Path

    @classmethod
    def create(cls, root: str | Path) -> "RunStore":
        resolved = Path(root).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "candidates").mkdir(exist_ok=True)
        return cls(resolved)

    @property
    def candidates(self) -> Path:
        return self.root / "candidates"

    @property
    def evidence_file(self) -> Path:
        return self.root / "evidence.jsonl"

    def write_json(self, name: str, payload: Any) -> Path:
        target = self.root / name
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target

    def archive_agent_workspace(
        self,
        workspace: str | Path,
    ) -> dict[str, list[str]]:
        source_root = Path(workspace).resolve()
        destination = self.root / "workspace"
        destination.mkdir(exist_ok=True)
        report: dict[str, list[str]] = {"copied": [], "preserved": [], "skipped": []}
        for source in source_root.rglob("*"):
            relative = source.relative_to(source_root)
            name = relative.as_posix()
            if relative.parts[0] == ".avo_rpc" or source.is_symlink():
                report["skipped"].append(name)
                continue
            if not source.is_file():
                continue
            try:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                report["copied"].append(name)
            except OSError as exc:
                if (destination / relative).is_file():
                    report["preserved"].append(name)
                else:
                    report["skipped"].append(f"{name}: {exc}")
        self.write_json("workspace_archive.json", report)
        return report
