from __future__ import annotations

import difflib
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from avo.core.framework import JsonValue, _jsonable
from avo.evolution.candidate import (
    CandidateEvaluation,
    RunCandidate,
    validate_candidate_id,
)


_INHERITANCE_EXCLUDES = {
    ".codex",
    ".agents",
    ".tmp",
    "observations",
    "AGENTS.md",
    "AGENTS.override.md",
    ".avo_rpc",
    "__pycache__",
    "AGENT_INTERFACE.md",
    "MISSION.md",
    "agent_transcript.jsonl",
    "avo_tool.py",
    "drafts",
}


def _solver_details(path: Path) -> tuple[str | None, str | None]:
    if not path.is_file():
        return None, None
    source = path.read_text(encoding="utf-8", errors="replace")[:100_000]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return source, digest


def _trace_summary(run_dir: Path) -> dict[str, JsonValue] | None:
    evidence_path = next(
        (
            path
            for path in (
                run_dir / "evaluation" / "evidence.jsonl",
                run_dir / "solver_evaluation" / "evidence.jsonl",
                run_dir / "evidence.jsonl",
            )
            if path.is_file()
        ),
        None,
    )
    if evidence_path is None:
        return None

    transitions: list[dict[str, Any]] = []
    for line in evidence_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "transition" and isinstance(event.get("payload"), dict):
            transitions.append(event["payload"])
    if not transitions:
        return None

    def level(observation: Any) -> int:
        if not isinstance(observation, dict):
            return 0
        progress = observation.get("progress", {})
        if not isinstance(progress, dict):
            return 0
        try:
            return int(progress.get("levels_completed", 0))
        except (TypeError, ValueError):
            return 0

    def comparable_observation(observation: Any) -> Any:
        if not isinstance(observation, dict):
            return observation
        comparable = dict(observation)
        metadata = comparable.get("metadata")
        if isinstance(metadata, dict) and "rendered_frame" in metadata:
            comparable_metadata = dict(metadata)
            comparable_metadata.pop("rendered_frame", None)
            if comparable_metadata:
                comparable["metadata"] = comparable_metadata
            else:
                comparable.pop("metadata", None)
        return comparable

    deepest_level = max(
        max(level(item.get("before")), level(item.get("after")))
        for item in transitions
    )
    deepest = [item for item in transitions if level(item.get("before")) == deepest_level]
    action_counts = Counter(
        str(item.get("action", {}).get("id", "unknown")) for item in deepest
    )
    observations = {
        hashlib.sha256(
            json.dumps(
                comparable_observation(item.get("before")),
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        for item in deepest
    }
    return {
        "transitions": len(transitions),
        "deepest_level": deepest_level,
        "actions_at_deepest_level": len(deepest),
        "unchanged_actions_at_deepest_level": sum(
            comparable_observation(item.get("before"))
            == comparable_observation(item.get("after"))
            for item in deepest
        ),
        "unique_observations_at_deepest_level": len(observations),
        "action_counts_at_deepest_level": dict(sorted(action_counts.items())),
    }


class EvolutionStore:
    """Framework-owned immutable candidates and append-only evaluation records."""

    def __init__(self, root: str | Path, optimizer_workspace: str | Path) -> None:
        self.root = Path(root).resolve()
        self.optimizer_workspace = Path(optimizer_workspace).resolve()
        legacy_population = self.root / "population.json"
        self.legacy_layout = legacy_population.exists() and not (
            self.root / "lineage.json"
        ).exists()
        self.candidates_dir = (
            self.root / "candidates" if self.legacy_layout else self.root
        )
        self.evaluations_dir = (
            self.root / "evaluations" if self.legacy_layout else self.root
        )
        self.population_path = (
            legacy_population if self.legacy_layout else self.root / "lineage.json"
        )
        self.drafts_dir = self.optimizer_workspace / "drafts"
        self.root.mkdir(parents=True, exist_ok=True)
        if self.legacy_layout:
            self.candidates_dir.mkdir(parents=True, exist_ok=True)
            self.evaluations_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        if not self.population_path.exists():
            self._save({"schema_version": 1, "candidates": [], "evaluations": []})

    @classmethod
    def create(
        cls,
        root: str | Path,
        optimizer_workspace: str | Path | None = None,
    ) -> "EvolutionStore":
        resolved = Path(root).resolve()
        workspace = (
            Path(optimizer_workspace).resolve()
            if optimizer_workspace is not None
            else resolved / "outer"
        )
        return cls(resolved, workspace)

    def _load(self) -> dict[str, Any]:
        payload = json.loads(self.population_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("Unsupported evolution lineage schema")
        return payload

    def _save(self, payload: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / f".population-{uuid4().hex}.tmp"
        temporary.write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
        temporary.replace(self.population_path)

    def candidates(self) -> tuple[RunCandidate, ...]:
        records = self._load()["candidates"]
        return tuple(self.get_candidate(str(item["candidate_id"])) for item in records)

    def get_candidate(self, candidate_id: str) -> RunCandidate:
        safe_id = validate_candidate_id(candidate_id)
        candidate = RunCandidate.load(self.candidates_dir / safe_id)
        if candidate.candidate_id != safe_id:
            raise ValueError("Candidate directory and manifest IDs do not match")
        return candidate

    def register_draft(self, candidate_id: str) -> RunCandidate:
        safe_id = validate_candidate_id(candidate_id)
        draft = (self.drafts_dir / safe_id).resolve()
        if draft.parent != self.drafts_dir:
            raise ValueError("Draft must be directly inside optimizer_workspace/drafts")
        candidate = RunCandidate.load(draft)
        if candidate.candidate_id != safe_id:
            raise ValueError("Draft directory and manifest IDs do not match")
        existing_ids = {item.candidate_id for item in self.candidates()}
        if safe_id in existing_ids or (self.candidates_dir / safe_id).exists():
            raise ValueError(f"Registered candidate is immutable: {safe_id}")
        missing_parents = [parent for parent in candidate.parent_ids if parent not in existing_ids]
        if missing_parents:
            raise ValueError(f"Unknown parent candidates: {', '.join(missing_parents)}")

        temporary = self.candidates_dir / f".{safe_id}-{uuid4().hex}.tmp"
        try:
            shutil.copytree(draft, temporary)
            admitted = RunCandidate.load(temporary)
            temporary.rename(self.candidates_dir / safe_id)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise

        payload = self._load()
        payload["candidates"].append(
            {
                **admitted.record(),
                "path": str(self.candidates_dir / safe_id),
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._save(payload)
        shutil.rmtree(draft)
        return self.get_candidate(safe_id)

    def create_seed(
        self,
        candidate_id: str,
        strategy: str,
        notes: str = "# Candidate knowledge\n\nNo prior run evidence.\n",
    ) -> RunCandidate:
        self.prepare_seed_draft(candidate_id, strategy, notes)
        return self.register_draft(candidate_id)

    def prepare_seed_draft(
        self,
        candidate_id: str,
        strategy: str = "",
        notes: str = "# Candidate knowledge\n\nNo prior run evidence.\n",
    ) -> dict[str, JsonValue]:
        safe_id = validate_candidate_id(candidate_id)
        draft = self.drafts_dir / safe_id
        if draft.exists() or (self.candidates_dir / safe_id).exists():
            raise ValueError(f"Candidate already exists: {safe_id}")
        seed_name = "workspace" if self.legacy_layout else "seed"
        (draft / seed_name).mkdir(parents=True)
        (draft / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "candidate_id": safe_id,
                    "parent_ids": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (draft / "STRATEGY.md").write_text(strategy.strip() + "\n", encoding="utf-8")
        (draft / seed_name / "NOTES.md").write_text(notes, encoding="utf-8")
        return {"draft_candidate_id": safe_id, "draft_path": str(draft)}

    def evaluations(self, candidate_id: str | None = None) -> tuple[dict[str, Any], ...]:
        records = tuple(dict(item) for item in self._load()["evaluations"])
        if candidate_id is None:
            return records
        safe_id = validate_candidate_id(candidate_id)
        return tuple(item for item in records if item["candidate_id"] == safe_id)

    def latest_evaluation(self, candidate_id: str) -> dict[str, Any] | None:
        records = self.evaluations(candidate_id)
        return records[-1] if records else None

    def next_run_dir(self, candidate_id: str) -> Path:
        safe_id = validate_candidate_id(candidate_id)
        if not self.legacy_layout:
            if self.evaluations(safe_id):
                raise ValueError(f"{safe_id} is already evaluated")
            return self.root / safe_id
        number = len(self.evaluations(safe_id)) + 1
        return self.evaluations_dir / safe_id / f"run_{number:03d}"

    def record_evaluation(self, evaluation: CandidateEvaluation) -> None:
        self.get_candidate(evaluation.candidate_id)
        run_dir = evaluation.run_dir.resolve()
        if self.legacy_layout:
            expected_parent = (self.evaluations_dir / evaluation.candidate_id).resolve()
            valid_location = run_dir.parent == expected_parent
            summary_path = run_dir / "final_summary.json"
        else:
            valid_location = run_dir == (self.root / evaluation.candidate_id).resolve()
            summary_path = run_dir / "summary.json"
        if not valid_location:
            raise ValueError("Evaluation run directory is outside the trusted store")
        if not summary_path.is_file():
            raise ValueError(f"Evaluation is missing {summary_path.name}")
        payload = self._load()
        if any(
            item["candidate_id"] == evaluation.candidate_id
            and item["evaluation_id"] == evaluation.evaluation_id
            for item in payload["evaluations"]
        ):
            raise ValueError("Evaluation is already recorded")
        payload["evaluations"].append(evaluation.record())
        self._save(payload)

    def fork(self, parent_id: str, child_id: str) -> dict[str, JsonValue]:
        parent = self.get_candidate(parent_id)
        safe_child = validate_candidate_id(child_id)
        if (self.candidates_dir / safe_child).exists() or (self.drafts_dir / safe_child).exists():
            raise ValueError(f"Candidate or draft already exists: {safe_child}")
        latest = self.latest_evaluation(parent.candidate_id)
        if latest is None:
            raise ValueError(f"Evaluate {parent.candidate_id} before forking it")
        parent_run = Path(str(latest["run_dir"]))
        source_workspace = (
            parent_run / "workspace"
            if self.legacy_layout
            else parent_run / "solver"
        )
        if not source_workspace.is_dir():
            raise ValueError("Parent evaluation has no archived workspace")

        draft = self.drafts_dir / safe_child
        (draft / "seed").mkdir(parents=True)
        shutil.copy2(parent.strategy_path, draft / "STRATEGY.md")
        for source in source_workspace.rglob("*"):
            relative = source.relative_to(source_workspace)
            if source.is_symlink() or any(part in _INHERITANCE_EXCLUDES for part in relative.parts):
                continue
            if not source.is_file():
                continue
            target = draft / "seed" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        (draft / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "candidate_id": safe_child,
                    "parent_ids": [parent.candidate_id],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "draft_candidate_id": safe_child,
            "parent_id": parent.candidate_id,
            "draft_path": str(draft),
            "inherited_from_evaluation": str(latest["evaluation_id"]),
        }

    def inspect(self, candidate_id: str) -> dict[str, JsonValue]:
        candidate = self.get_candidate(candidate_id)
        files = []
        if candidate.workspace_path.is_dir():
            files = sorted(
                path.relative_to(candidate.workspace_path).as_posix()
                for path in candidate.workspace_path.rglob("*")
                if path.is_file()
            )
        latest = self.latest_evaluation(candidate.candidate_id)
        final_summary: JsonValue = None
        learned_notes: dict[str, JsonValue] = {}
        solver_source: str | None = None
        solver_sha256: str | None = None
        parent_solver_sha256: str | None = None
        solver_diff: str | None = None
        trace_summary: dict[str, JsonValue] | None = None
        if latest is not None:
            run_dir = Path(str(latest["run_dir"]))
            summary_path = run_dir / (
                "final_summary.json" if self.legacy_layout else "summary.json"
            )
            if summary_path.is_file():
                final_summary = _jsonable(
                    json.loads(summary_path.read_text(encoding="utf-8"))
                )
            final_workspace = run_dir / (
                "workspace" if self.legacy_layout else "solver"
            )
            solver_source, solver_sha256 = _solver_details(final_workspace / "solver.py")
            trace_summary = _trace_summary(run_dir)
            if candidate.parent_ids:
                parent_id = candidate.parent_ids[0]
                parent_latest = self.latest_evaluation(parent_id)
                if parent_latest is not None:
                    parent_run = Path(str(parent_latest["run_dir"]))
                    parent_workspace = parent_run / (
                        "workspace" if self.legacy_layout else "solver"
                    )
                    parent_source, parent_solver_sha256 = _solver_details(
                        parent_workspace / "solver.py"
                    )
                    if parent_source is not None and solver_source is not None:
                        solver_diff = "".join(
                            difflib.unified_diff(
                                parent_source.splitlines(keepends=True),
                                solver_source.splitlines(keepends=True),
                                fromfile=f"{parent_id}/solver.py",
                                tofile=f"{candidate.candidate_id}/solver.py",
                            )
                        )[:100_000]
            if final_workspace.is_dir():
                note_files = sorted(
                    path
                    for path in final_workspace.rglob("*.md")
                    if path.is_file()
                    and not path.is_symlink()
                    and path.name not in _INHERITANCE_EXCLUDES
                )[:20]
                for path in note_files:
                    relative = path.relative_to(final_workspace).as_posix()
                    learned_notes[relative] = path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )[:100_000]
        return {
            "candidate": candidate.record(),
            "strategy": candidate.strategy(),
            "workspace_files": files,
            "evaluations": _jsonable(self.evaluations(candidate.candidate_id)),
            "latest_run": {
                "final_summary": final_summary,
                "learned_notes": learned_notes,
                "solver": {
                    "sha256": solver_sha256,
                    "parent_sha256": parent_solver_sha256,
                    "source": solver_source,
                    "diff_from_parent": solver_diff,
                },
                "trace_summary": trace_summary,
            },
        }

    def evidence(
        self,
        candidate_id: str,
        phase: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, JsonValue]:
        safe_id = validate_candidate_id(candidate_id)
        valid_phases = {"research", "evaluation", "self_check_01", "self_check_02"}
        if phase not in valid_phases:
            raise ValueError(
                "phase must be research, evaluation, self_check_01, or self_check_02"
            )
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        latest = self.latest_evaluation(safe_id)
        if latest is None:
            raise ValueError(f"Evaluate {safe_id} before reading its evidence")
        run_dir = Path(str(latest["run_dir"]))
        if phase.startswith("self_check_"):
            research_dir = run_dir if self.legacy_layout else run_dir / "research"
            check_number = int(phase.rsplit("_", 1)[1])
            evidence_path = (
                research_dir
                / "self_check"
                / f"check_{check_number:02d}"
                / "evidence.jsonl"
            )
        elif self.legacy_layout:
            evidence_path = (
                run_dir / "evidence.jsonl"
                if phase == "research"
                else run_dir / "solver_evaluation" / "evidence.jsonl"
            )
        else:
            evidence_path = run_dir / phase / "evidence.jsonl"
        if not evidence_path.is_file():
            raise ValueError(f"{safe_id} has no saved {phase} evidence")

        events: list[JsonValue] = []
        for line in evidence_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            try:
                events.append(_jsonable(json.loads(line)))
            except json.JSONDecodeError:
                continue
        page = events[offset : offset + limit]
        next_offset = offset + len(page)
        return {
            "candidate_id": safe_id,
            "phase": phase,
            "offset": offset,
            "limit": limit,
            "total_events": len(events),
            "next_offset": next_offset if next_offset < len(events) else None,
            "events": page,
        }

    def population_summary(self) -> dict[str, JsonValue]:
        candidates = self.candidates()
        evaluations = self.evaluations()
        best = max(evaluations, key=lambda item: float(item["fitness"]), default=None)
        return {
            "candidates": [candidate.record() for candidate in candidates],
            "evaluations": _jsonable(evaluations),
            "candidate_count": len(candidates),
            "evaluation_count": len(evaluations),
            "drafts": sorted(
                path.name for path in self.drafts_dir.iterdir() if path.is_dir()
            ),
            "best": _jsonable(best),
        }
