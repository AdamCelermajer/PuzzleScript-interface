"""Read existing run artifacts without moving them or treating old status as liveness."""
from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOTS = ("output", "avo/output", "studies/codex_agent/output")
SKIP = {"controller", "workspace", "codex_workspace", "research", "evaluation", "solver",
        "seed", "analysis", "optimizer_analysis", "frames", "model_requests", "node_modules"}


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def legacy_enqueue_backend(config: dict) -> bool:
    settings = config.get("profile_settings") or {}
    return (settings.get("game_id") == "ps_enqueue-v1"
            and str(settings.get("backend_url", "")).rstrip("/") in {
                "http://host.docker.internal:8000", "http://localhost:8000", "http://127.0.0.1:8000"
            })


def last_record(path: Path) -> dict:
    """Bounded tail, including tolerance for a writer's incomplete last line."""
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 512_000))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
    except OSError:
        pass
    return {}


def run_path(run_id: str, root: Path = ROOT) -> Path:
    if not run_id or "\\" in run_id or any(p in {"", ".", ".."} for p in run_id.split("/")):
        raise ValueError("Invalid run ID")
    path = (root / run_id).resolve()
    if not any(path.is_relative_to((root / base).resolve()) for base in RUN_ROOTS):
        raise ValueError("Run is outside the artifact roots")
    # A link inside an archive must not expose another run or private directory.
    cursor = root
    for part in Path(run_id).parts:
        cursor = cursor / part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ValueError("Linked artifact directories are not supported")
    return path


def _linked(entry: os.DirEntry) -> bool:
    return entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction())


def discover(root: Path = ROOT) -> tuple[list[Path], list[Path]]:
    runs, jobs = [], []

    # One directory listing per folder; DirEntry type checks avoid a stat per probe.
    def visit(path: Path, depth: int) -> None:
        try:
            with os.scandir(path) as listing:
                entries = {entry.name: entry for entry in listing}
        except OSError:
            return

        def is_file(name: str) -> bool:
            entry = entries.get(name)
            try:
                return entry is not None and entry.is_file()
            except OSError:
                return False

        if is_file("job.json"):
            jobs.append(path)
        if is_file("evolution_config.json"):
            runs.append(path)
            return
        config = read_json(path / "run_config.json") if is_file("run_config.json") else {}
        if config and ("condition" in config or config.get("agent_mode") == "codex" or
                       "codex_session.jsonl" in entries):
            runs.append(path)
            return
        if depth == 0:
            return
        for name, entry in entries.items():
            try:
                is_directory = entry.is_dir() and not _linked(entry)
            except OSError:
                continue
            if is_directory and name not in SKIP and not name.startswith((".", "x_")):
                visit(path / name, depth - 1)

    for base in RUN_ROOTS:
        path = root / base
        if not (path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())):
            visit(path, 5)
    return sorted(set(runs)), sorted(set(jobs))


def live_containers() -> tuple[dict[str, str], str | None]:
    try:
        listing = subprocess.run(["docker", "ps", "--filter", "name=avo-", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=5, check=True)
        names = [name for name in listing.stdout.split() if name.startswith("avo-isolated-")]
        if not names:
            return {}, None
        result = subprocess.run(["docker", "inspect", "--format", "{{.Name}} {{json .Mounts}}", *names],
                                capture_output=True, text=True, timeout=5, check=True)
        mounts = {}
        for line in result.stdout.splitlines():
            name, value = line.split(" ", 1)
            for mount in json.loads(value):
                if mount.get("Destination") == "/results":
                    mounts[str(Path(mount["Source"]).resolve()).casefold()] = name.lstrip("/")
        return mounts, None
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}, "Docker process status unavailable; saved status is not proof a campaign is running."


def modified(paths: list[Path]) -> float:
    values = []
    for path in paths:
        try:
            values.append(path.stat().st_mtime)
        except OSError:
            pass
    return max(values, default=0)


def agent_identity(config: dict) -> dict:
    """Preserve recorded identities, including experiments from retired runners."""
    backend = config.get("agent_backend", "codex")
    backend = ("opencode" if backend in {"opencode", "OpenCodeAgent"}
               else config.get("harness") if config.get("harness") in {"tools", "raw"} else "codex")
    model = (config.get("player") or {}).get("model", config.get("model"))
    outer = config.get("optimizer_model")
    def provider(value):
        return value.split("/", 1)[0] if value and "/" in value and (backend == "opencode" or value.startswith(("openrouter/", "nanogpt/"))) else "openai"
    return {"agent_backend": backend, "model": model, "model_provider": provider(model),
            "optimizer_model": outer, "optimizer_provider": provider(outer) if outer else None}


def result_inputs(config: dict, evaluations: list[dict], finalized: bool) -> dict:
    """Only the fields the browser results projection reads, so result pages need
    no per-run archive requests."""
    def get(value, *keys):
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
        return value

    def compact(e: dict) -> dict:
        score = e.get("score") or {}
        return {"candidate_id": e.get("candidate_id"), "fitness": e["fitness"], "success": e.get("success"),
                "environment_steps": e.get("environment_steps"), "finish_reason": e.get("finish_reason"),
                "score": {"win_levels": get(score, "win_levels"),
                          "environment_task": {"score": {"win_levels": get(score, "environment_task", "score", "win_levels")}},
                          "research_score": {"win_levels": get(score, "research_score", "win_levels")},
                          "research_environment_actions": get(score, "research_environment_actions"),
                          "search_session_elapsed_seconds": get(score, "search_session_elapsed_seconds")}}

    player = config.get("player") or {}
    return {"config": {"player": {k: player.get(k) for k in ("effort", "max_environment_steps", "max_wall_seconds")},
                       "optimizer_effort": config.get("optimizer_effort"), "max_evaluations": config.get("max_evaluations"),
                       "fresh_solver_max_environment_steps": config.get("fresh_solver_max_environment_steps"),
                       "initial_observation": {"progress": {"win_levels": get(config, "initial_observation", "progress", "win_levels")}}},
            "evaluations": [compact(e) for e in evaluations
                            if isinstance(e.get("fitness"), (int, float)) and not isinstance(e["fitness"], bool)
                            and math.isfinite(e["fitness"])],
            "finalized": finalized}


def snapshot(root: Path = ROOT, containers: dict | None = None) -> dict:
    paths, job_paths = discover(root)
    warnings = []
    if containers is None:
        containers, warning = live_containers()
        if warning:
            warnings.append(warning)
    jobs, owners = [], {}
    for path in job_paths:
        job = read_json(path / "job.json")
        heartbeat = job.get("heartbeat", 0)
        fresh = isinstance(heartbeat, (int, float)) and time.time() - heartbeat < 20
        status = job.get("status", "unknown")
        if status in {"starting", "running", "stopping"} and not fresh:
            status = "unconfirmed"
        job_id = path.relative_to(root).as_posix()
        kind = job.get("config", {}).get("kind")
        resumable = kind == "avo" and status in {"paused", "cancelled", "failed"} and not job.get("resumed_as")
        dismissed = job.get("dismissed_from_runs_at")
        jobs.append({"id": job_id, "kind": kind, "status": status,
                     "comparison": job.get("config", {}).get("comparison", False),
                     "created_at": job.get("created_at"), "parallel": job.get("config", {}).get("parallel"),
                     "error": job.get("error"), "runs": job.get("runs", []),
                     "can_pause": kind == "avo" and fresh and status in {"starting", "running"},
                     "can_stop": fresh and status in {"starting", "running"}, "can_resume": resumable,
                     "can_dismiss": resumable and not dismissed,
                     "dismissed_from_runs_at": dismissed,
                     "recovery_of": job.get("recovery_of"), "resumed_as": job.get("resumed_as")})
        for row in job.get("runs", []):
            owners[row.get("id")] = (job_id, row, fresh)
    rows = []
    terminal_children = {}
    for path in paths:
        run_id = path.relative_to(root).as_posix()
        is_avo = (path / "evolution_config.json").is_file()
        config = read_json(path / ("evolution_config.json" if is_avo else "run_config.json"))
        owner = owners.get(run_id)
        recovery = read_json(path.parent / "recovery.json") if is_avo and owner else {}
        container = containers.get(str(path.parent.resolve()).casefold()) if is_avo else None
        status, status_source = "unconfirmed", "No current process confirmation"
        if owner:
            status = owner[1].get("status", "queued")
            status_source = "Batch worker heartbeat" if owner[2] else "Saved batch record"
            if not owner[2] and status in {"running", "starting", "queued"}:
                status = "unconfirmed"
        if container:
            status, status_source = "running", "Docker reports the campaign container running"
        result = read_json(path / ("evolution_summary.json" if is_avo else "result.json"))
        error = read_json(path / "error.json")
        legacy_enqueue = is_avo and legacy_enqueue_backend(config)
        needs_assistance = error.get("status") == "needs_assistance" or (
            legacy_enqueue and owner is not None and owner[1].get("status") == "failed"
        )
        assistance_reason = error.get("error") or (
            "This Enqueue campaign used the legacy engine backend. Start a new campaign on port 8001."
            if legacy_enqueue else None
        )
        lineage = read_json(path / "lineage.json") if is_avo else {}
        evaluations = [e for e in lineage.get("evaluations", []) if isinstance(e, dict)]
        candidates = [e for e in lineage.get("candidates", []) if isinstance(e, dict)]
        candidate = candidates[-1].get("candidate_id", "") if candidates else ""
        if not candidate.startswith("x_") or not candidate[2:].isdigit():
            candidate = ""
        current = path / candidate if candidate else path
        if result and not container and not (owner and owner[2] and status == "running"):
            status, status_source = result.get("status", "completed"), "Final result artifact"
            if is_avo and config.get("world_model_mode", "off") != "off" and not (path / "world_model.md").is_file():
                status, status_source = "failed", "Required final world_model.md missing"
        elif error and not container:
            status, status_source = "failed", "Needs assistance: infrastructure failure" if needs_assistance else "Error artifact"
        if needs_assistance and status == "failed" and not container:
            status_source = "Needs assistance: inspect the failure before a new campaign"
        if result:
            terminal_children[run_id] = status if status in {"completed", "failed"} else "completed"
        elif error:
            terminal_children[run_id] = "failed"
        transition = last_record(path / "transitions.jsonl") if not is_avo else {}
        fitness = [e["fitness"] for e in evaluations if isinstance(e.get("fitness"), (int, float))]
        solved = result.get("success" if is_avo else "solved") is True or any(e.get("success") is True for e in evaluations)
        activity = modified([path / "run_config.json", path / "evolution_config.json", path / "lineage.json",
                             path / "result.json", path / "evolution_summary.json", path / "transitions.jsonl",
                             current / "research/evidence.jsonl", current / "evaluation/evidence.jsonl",
                             path / "optimizer_analysis/conversation.jsonl"])
        batch = owner[0] if owner else ("/".join(run_id.split("/")[:2]) if run_id.startswith("output/avo-") else str(path.parent.relative_to(root)).replace("\\", "/"))
        rows.append({"id": run_id, "kind": "avo" if is_avo else "codex", "batch": batch,
                     **agent_identity(config),
                     "log_href": f"/api/workbench/experiments/log?job={quote(owner[0], safe='')}&run={quote(Path(owner[1]['output']).name)}" if owner else None,
                     "game_id": (config.get("profile_settings") or {}).get("game_id") if is_avo else config.get("game_id"),
                     "model": (config.get("player") or {}).get("model") if is_avo else config.get("model"),
                     "condition": config.get("condition", "baseline") if not is_avo else None,
                     "world_model_mode": config.get("world_model_mode", "not-recorded") if is_avo else None,
                     "status": status, "status_source": status_source, "container": container,
                     "needs_assistance": needs_assistance,
                     "failure_reason": assistance_reason if needs_assistance else None,
                     "can_resume": bool(is_avo and owner and owner[1].get("status") == "failed"
                                        and not recovery.get("resumed_as") and not container and not needs_assistance),
                     "resumed_as": recovery.get("resumed_as"),
                     "solved": solved, "has_result": bool(result), "best_fitness": max(fitness) if fitness else None,
                     "levels": result.get("levels_completed", transition.get("after", {}).get("levels_completed")) if not is_avo else None,
                     "actions": result.get("action_count", transition.get("action_index")) if not is_avo else None,
                     "evaluated": len(evaluations), "budget": config.get("max_evaluations" if is_avo else "max_steps"),
                     "candidate": candidate or None, "modified": activity * 1000,
                     "can_continue": not is_avo and result.get("reason") == "step_budget_exhausted" and not solved,
                     "href": f"/experiments/avo-lab.html?run={quote(run_id, safe='')}" if is_avo else f"/runs/detail.html?run={quote(run_id, safe='')}",
                     "config": config if not is_avo else {"player": config.get("player"), "optimizer_model": config.get("optimizer_model")},
                     **({"result_inputs": result_inputs(config, evaluations, bool(result))} if is_avo else
                        {"recorded_win_levels": next((v for v in (result.get("win_levels"), (transition.get("after") or {}).get("win_levels")) if v is not None), None)})})
    # Queued children have no artifacts yet, but still belong in their batch.
    present = {r["id"] for r in rows}
    for run_id, (job_id, row, fresh) in owners.items():
        if run_id not in present:
            public_row = {k: v for k, v in row.items() if k not in {"command", "output"}}
            rows.append({**public_row, "batch": job_id, "modified": 0, "status": row.get("status", "queued") if fresh or row.get("status") in {"paused", "cancelled", "failed", "completed"} else "unconfirmed", "status_source": "Batch worker", "solved": False,
                         "log_href": f"/api/workbench/experiments/log?job={quote(job_id, safe='')}&run={quote(Path(row.get('output', '')).name)}"})
    # A worker can disappear after its children have already written their final
    # artifacts, leaving the append-only job manifest with a stale "running"
    # status. Reconcile only the API snapshot: historical manifests stay intact,
    # and a job remains unconfirmed until every declared child is terminal.
    for job in jobs:
        child_ids = [row.get("id") for row in job.get("runs", [])]
        job["needs_assistance"] = any(row.get("needs_assistance") for row in rows if row["id"] in child_ids)
        if job["needs_assistance"]:
            job["can_resume"] = False
        if job["status"] == "unconfirmed" and child_ids and all(child_id in terminal_children for child_id in child_ids):
            job["status"] = "failed" if any(terminal_children[child_id] == "failed" for child_id in child_ids) else "completed"
            job["status_source"] = "Terminal child artifacts"
    rows.sort(key=lambda r: (r["status"] == "running", r.get("modified", 0)), reverse=True)
    return {"runs": rows, "jobs": jobs, "warnings": warnings, "checked_at": time.time()}
