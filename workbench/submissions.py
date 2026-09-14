"""Read the evaluated submission, never a newer seed or research workspace."""
from __future__ import annotations

import math
import re
from pathlib import Path

from workbench.catalog import ROOT, agent_identity, read_json, run_path

EXCLUDED = {"__pycache__", "observations"}


def submission(run: str, root: Path = ROOT, candidate: str = "") -> dict:
    explicit_candidate = bool(candidate)
    path = run_path(run, root)
    if not (path / "evolution_config.json").is_file():
        raise ValueError("AVO campaign not found")
    lineage = read_json(path / "lineage.json") or read_json(path / "population.json")
    evaluations = [e for e in lineage.get("evaluations", []) if isinstance(e, dict)
                   and isinstance(e.get("fitness"), (int, float)) and math.isfinite(e["fitness"])]
    # Match EvolutionStore: highest fitness, earliest evaluated candidate on a tie.
    best = max(evaluations, key=lambda e: e["fitness"], default=None)
    if candidate:
        best = next((e for e in evaluations if e.get("candidate_id") == candidate), None)
        if best is None:
            raise ValueError("Candidate has no completed evaluation")
    files = []
    solver_root = None
    if best:
        candidate, evaluation = str(best.get("candidate_id", "")), str(best.get("evaluation_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", candidate):
            raise ValueError("Invalid evaluated candidate ID")
        relative = candidate + "/solver"
        if (path / "population.json").exists() and not (path / "lineage.json").exists():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", evaluation):
                raise ValueError("Invalid evaluation ID")
            relative = "evaluations/" + candidate + "/" + evaluation + "/workspace"
        solver_root = run_path(run + "/" + relative, root)
        for target in sorted(solver_root.rglob("*")):
            rel = target.relative_to(solver_root)
            if any(p.startswith(".") or p in EXCLUDED for p in rel.parts):
                continue
            safe = run_path(run + "/" + relative + "/" + rel.as_posix(), root)
            if safe.is_file():
                files.append({"name": rel.as_posix(), "path": relative + "/" + rel.as_posix(), "size": safe.stat().st_size})
    model = run_path(run + "/world_model.md", root)
    config = read_json(path / "evolution_config.json")
    first_success = next(((i, e) for i, e in enumerate(evaluations, 1) if e.get("success")), None)
    return {"id": run, "selection": "candidate" if explicit_candidate else "best", "game_id": config.get("profile_settings", {}).get("game_id"),
            **agent_identity(config),
            "mode": config.get("world_model_mode", "not-recorded"),
            "finalized": bool(read_json(path / "evolution_summary.json")),
            "best": best, "evaluations": evaluations, "files": files,
            "evaluations_to_success": first_success[0] if first_success else None,
            "seconds_to_success": first_success[1].get("score", {}).get("search_session_elapsed_seconds") if first_success else None,
            "solver_present": any(f["name"] == "solver.py" for f in files),
            "world_model": "world_model.md" if model.is_file() else None,
            "world_model_record": read_json(path / "world_model.json")}


def submission_file(run: str, file: str, root: Path = ROOT) -> Path:
    parts = file.split("/")
    candidate = (parts[1] if parts[0] == "evaluations" and len(parts) > 1 else parts[0]) if file != "world_model.md" else ""
    record = submission(run, root, candidate)
    allowed = {f["path"] for f in record["files"]}
    if record["world_model"]:
        allowed.add(record["world_model"])
    if file not in allowed:
        raise ValueError("File is not part of this evaluated submission")
    return run_path(run + "/" + file, root)
