from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from frameworks.avo.core.framework import JsonValue, _jsonable


_CANDIDATE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
_RESERVED_WORKSPACE_PARTS = {".avo_rpc", "__pycache__", ".codex", ".agents"}
_RESERVED_WORKSPACE_FILES = {
    "AGENT_INTERFACE.md",
    "MISSION.md",
    "agent_transcript.jsonl",
    "avo_tool.py",
    "AGENTS.md",
    "AGENTS.override.md",
}


def validate_candidate_id(candidate_id: str) -> str:
    value = candidate_id.strip()
    if not _CANDIDATE_ID.fullmatch(value):
        raise ValueError("candidate_id must be a safe 1-80 character identifier")
    return value


@dataclass(frozen=True)
class RunCandidate:
    candidate_id: str
    parent_ids: tuple[str, ...]
    root: Path

    @classmethod
    def load(cls, root: str | Path) -> "RunCandidate":
        resolved = Path(root).resolve()
        manifest_path = resolved / "manifest.json"
        strategy_path = resolved / "STRATEGY.md"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("Run candidate requires a regular manifest.json")
        if not strategy_path.is_file() or strategy_path.is_symlink():
            raise ValueError("Run candidate requires a regular STRATEGY.md")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("manifest.json must contain valid JSON") from exc
        if not isinstance(manifest, Mapping) or manifest.get("schema_version") != 1:
            raise ValueError("manifest.json schema_version must be 1")

        candidate_id = validate_candidate_id(str(manifest.get("candidate_id", "")))
        raw_parents = manifest.get("parent_ids", [])
        if not isinstance(raw_parents, list):
            raise ValueError("manifest.json parent_ids must be a list")
        parent_ids = tuple(validate_candidate_id(str(item)) for item in raw_parents)
        if len(parent_ids) != len(set(parent_ids)):
            raise ValueError("manifest.json parent_ids must be unique")
        if candidate_id in parent_ids:
            raise ValueError("A run candidate cannot be its own parent")

        workspace = resolved / ("seed" if (resolved / "seed").exists() else "workspace")
        if workspace.exists() and (not workspace.is_dir() or workspace.is_symlink()):
            raise ValueError("workspace must be a regular directory")
        if workspace.is_dir():
            for path in workspace.rglob("*"):
                relative = path.relative_to(workspace)
                if path.is_symlink() or path.is_junction():
                    raise ValueError(f"Candidate workspace cannot contain symlinks: {relative}")
                if any(part.casefold() in {v.casefold() for v in _RESERVED_WORKSPACE_PARTS} for part in relative.parts):
                    raise ValueError(f"Candidate workspace contains reserved path: {relative}")
                if relative.name.casefold() in {"agents.md", "agents.override.md"} or (len(relative.parts) == 1 and relative.name in _RESERVED_WORKSPACE_FILES):
                    raise ValueError(f"Candidate workspace contains reserved file: {relative}")
        return cls(candidate_id=candidate_id, parent_ids=parent_ids, root=resolved)

    @property
    def strategy_path(self) -> Path:
        return self.root / "STRATEGY.md"

    @property
    def workspace_path(self) -> Path:
        seed = self.root / "seed"
        return seed if seed.exists() else self.root / "workspace"

    def strategy(self) -> str:
        return self.strategy_path.read_text(encoding="utf-8").strip()

    def record(self) -> dict[str, JsonValue]:
        return {
            "candidate_id": self.candidate_id,
            "parent_ids": list(self.parent_ids),
            "path": str(self.root),
        }


@dataclass(frozen=True)
class CandidateEvaluation:
    evaluation_id: str
    candidate_id: str
    fitness: float
    success: bool
    terminal: bool
    score: Mapping[str, JsonValue]
    finish_reason: str
    environment_steps: int
    agent_turns: int
    run_dir: Path
    recorded_at: str

    def record(self) -> dict[str, JsonValue]:
        return {
            "evaluation_id": self.evaluation_id,
            "candidate_id": self.candidate_id,
            "fitness": self.fitness,
            "success": self.success,
            "terminal": self.terminal,
            "score": _jsonable(self.score),
            "finish_reason": self.finish_reason,
            "environment_steps": self.environment_steps,
            "agent_turns": self.agent_turns,
            "run_dir": str(self.run_dir),
            "recorded_at": self.recorded_at,
        }
