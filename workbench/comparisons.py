"""Compare explicit, matched AVO pairs from a single launch manifest."""
from __future__ import annotations

import math
from pathlib import Path

from workbench.catalog import ROOT, read_json, run_path, snapshot


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def comparison(job_id: str, root: Path = ROOT, live: dict | None = None) -> dict:
    directory = run_path(job_id, root)
    if directory.parent != root / "output/workbench":
        raise ValueError("Comparison must be a Workbench batch")
    job = read_json(directory / "job.json")
    config = job.get("config", {})
    if not config.get("comparison"):
        raise ValueError("This batch is not a matched comparison")
    live = live if live is not None else snapshot(root)
    statuses = {row["id"]: row for row in live["runs"]}
    pairs = {}
    for row in job.get("runs", []):
        pair_id = row.get("pair_id")
        mode = row.get("world_model_mode")
        if not pair_id or mode not in {"final-only", "between-hypotheses"}:
            continue
        pair = pairs.setdefault(pair_id, {"id": pair_id, "game_id": row["game_id"], "model": row["model"],
            "agent_backend": row.get("agent_backend", "codex"), "effort": row.get("effort"), "repeat": row["repeat"], "runs": {}})
        path = run_path(row["id"], root)
        lineage = read_json(path / "lineage.json")
        evaluations = [e for e in lineage.get("evaluations", []) if isinstance(e, dict) and number(e.get("fitness")) is not None]
        first_success = next(((i, e) for i, e in enumerate(evaluations, 1) if e.get("success") is True), None)
        best = max(evaluations, key=lambda e: e["fitness"], default=None)
        summary = read_json(path / "evolution_summary.json")
        status = statuses.get(row["id"], {}).get("status", "unconfirmed")
        pair["runs"][mode] = {"id": row["id"], "status": status, "finalized": bool(summary),
            "best_fitness": best["fitness"] if best else None, "best_candidate": best.get("candidate_id") if best else None,
            "solved": any(e.get("success") is True for e in evaluations), "evaluated": len(evaluations),
            "first_success_evaluation": first_success[0] if first_success else None,
            "seconds_to_success": number(first_success[1].get("score", {}).get("search_session_elapsed_seconds")) if first_success else None,
            "search_seconds": number(evaluations[-1].get("score", {}).get("search_session_elapsed_seconds")) if evaluations else None,
            "research_actions": sum(e.get("score", {}).get("research_environment_actions", 0) for e in evaluations)
                if evaluations and all(number(e.get("score", {}).get("research_environment_actions")) is not None for e in evaluations) else None,
            "solver_actions": best.get("environment_steps") if best else None,
            "finish_reason": summary.get("finish_reason") or (best.get("finish_reason") if best else None),
            "history": [{"candidate": e.get("candidate_id"), "fitness": e["fitness"]} for e in evaluations],
            "report_available": (path / "world_model.md").is_file()}
    return {"id": job_id, "created_at": job.get("created_at"), "config": config, "pairs": list(pairs.values())}
