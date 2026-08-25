from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from avo.core.framework import Action, Observation, Prediction, Transition, _jsonable


THEORY_PACKAGE_SCHEMA_VERSION = 1


def _observation(payload: dict) -> Observation:
    return Observation(
        payload=payload.get("payload"),
        status=str(payload.get("status", "UNKNOWN")),
        progress=payload.get("progress"),
        available_actions=tuple(str(item) for item in payload.get("available_actions", [])),
        metadata=dict(payload.get("metadata", {})),
    )


@dataclass(frozen=True)
class TheoryManifest:
    schema_version: int
    candidate_id: str
    parent_id: str | None
    claim: str
    complexity: float
    command: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "TheoryManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {"schema_version", "candidate_id", "claim", "complexity", "command"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"{path} is missing: {', '.join(missing)}")
        if payload["schema_version"] != THEORY_PACKAGE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Theory Package schema: {payload['schema_version']}")
        command = tuple(str(item) for item in payload["command"])
        if not command:
            raise ValueError(f"{path} command cannot be empty")
        return cls(
            schema_version=payload["schema_version"],
            candidate_id=str(payload["candidate_id"]).strip(),
            parent_id=str(payload["parent_id"]).strip() if payload.get("parent_id") else None,
            claim=str(payload["claim"]).strip(),
            complexity=float(payload["complexity"]),
            command=command,
        )


class FilesystemTheoryCandidate:
    """A language-neutral Theory Package invoked through a JSON subprocess protocol."""

    def __init__(self, package_dir: str | Path, timeout_seconds: float = 10) -> None:
        self.package_dir = Path(package_dir).resolve()
        self.manifest = TheoryManifest.load(self.package_dir / "manifest.json")
        self.candidate_id = self.manifest.candidate_id
        self.parent_id = self.manifest.parent_id
        self.claim = self.manifest.claim
        self.complexity = self.manifest.complexity
        self.timeout_seconds = timeout_seconds

    def _command(self) -> list[str]:
        command = list(self.manifest.command)
        if command[0] == "$PYTHON":
            command[0] = sys.executable
        executable = Path(command[-1]) if len(command) > 1 else None
        if executable and not executable.is_absolute() and not (self.package_dir / executable).exists():
            raise ValueError(f"Theory entrypoint does not exist: {executable}")
        return command

    def predict(
        self,
        history: Sequence[Transition],
        current: Observation,
        action: Action,
    ) -> Prediction:
        request = {
            "protocol": "avo-theory-predict-v1",
            "history": _jsonable(history),
            "current": _jsonable(current),
            "action": _jsonable(action),
        }
        completed = subprocess.run(
            self._command(),
            cwd=self.package_dir,
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()[-500:]
            raise RuntimeError(f"Theory process exited {completed.returncode}: {stderr}")
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("Theory process did not return one JSON object") from exc
        if response.get("protocol") != "avo-theory-prediction-v1":
            raise ValueError("Theory process returned an unsupported protocol")
        expected = response.get("expected")
        return Prediction(
            expected=_observation(expected) if isinstance(expected, dict) else None,
            confidence=float(response.get("confidence", 0)),
            rationale=str(response.get("rationale", "")),
        )


class TheoryPackageRegistry:
    """Discovers agent-created packages; it never generates candidates itself."""

    def __init__(self, root: str | Path, timeout_seconds: float = 10) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds

    def discover(self) -> tuple[FilesystemTheoryCandidate, ...]:
        candidates: list[FilesystemTheoryCandidate] = []
        for manifest in sorted(self.root.glob("*/manifest.json")):
            candidates.append(
                FilesystemTheoryCandidate(
                    manifest.parent,
                    timeout_seconds=self.timeout_seconds,
                )
            )
        ids = [candidate.candidate_id for candidate in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Theory Package candidate IDs must be unique")
        return tuple(candidates)
