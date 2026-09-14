"""Read existing run artifacts without moving them or treating old status as liveness."""
from __future__ import annotations

import json
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


def discover(root: Path = ROOT) -> tuple[list[Path], list[Path]]:
    runs, jobs = [], []

    def visit(path: Path, depth: int) -> None:
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            return
        if (path / "job.json").is_file():
            jobs.append(path)
        if (path / "evolution_config.json").is_file():
            runs.append(path)
            return
        config = read_json(path / "run_config.json")
        if config and ("condition" in config or config.get("agent_mode") == "codex" or
                       (path / "codex_session.jsonl").exists()):
            runs.append(path)
            return
        if depth == 0:
            return
        try:
            children = list(path.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir() and child.name not in SKIP and not child.name.startswith((".", "x_")):
                visit(child, depth - 1)

    for base in RUN_ROOTS:
        visit(root / base, 5)
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
    backend = "opencode" if backend in {"opencode", "OpenCodeAgent"} else "codex"
    model = (config.get("player") or {}).get("model", config.get("model"))
    outer = config.get("optimizer_model")
    def provider(value):
        return value.split("/", 1)[0] if value and "/" in value and (backend == "opencode" or value.startswith("openrouter/")) else "openai"
    return {"agent_backend": backend, "model": model, "model_provider": provider(model),
            "optimizer_model": outer, "optimizer_provider": provider(outer) if outer else None}


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
        jobs.append({"id": job_id, "kind": job.get("config", {}).get("kind"), "status": status,
                     "comparison": job.get("config", {}).get("comparison", False),
                     "created_at": job.get("created_at"), "parallel": job.get("config", {}).get("parallel"),
                     "error": job.get("error"), "runs": job.get("runs", []), "can_stop": fresh and status in {"starting", "running"}})
        for row in job.get("runs", []):
            owners[row.get("id")] = (job_id, row, fresh)
    rows = []
    for path in paths:
        run_id = path.relative_to(root).as_posix()
        is_avo = (path / "evolution_config.json").is_file()
        config = read_json(path / ("evolution_config.json" if is_avo else "run_config.json"))
        owner = owners.get(run_id)
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
        lineage = read_json(path / "lineage.json") if is_avo else {}
        evaluations = [e for e in lineage.get("evaluations", []) if isinstance(e, dict)]
        candidates = [e for e in lineage.get("candidates", []) if isinstance(e, dict)]
        candidate = candidates[-1].get("candidate_id", "") if candidates else ""
        if not candidate.startswith("x_") or not candidate[2:].isdigit():
            candidate = ""
        current = path / candidate if candidate else path
        if result and not container and not (owner and owner[2] and status == "running"):
            status, status_source = result.get("status", "completed"), "Final result artifact"
        elif error and not container:
            status, status_source = "failed", "Error artifact"
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
                     "solved": solved, "has_result": bool(result), "best_fitness": max(fitness) if fitness else None,
                     "levels": result.get("levels_completed", transition.get("after", {}).get("levels_completed")) if not is_avo else None,
                     "actions": result.get("action_count", transition.get("action_index")) if not is_avo else None,
                     "evaluated": len(evaluations), "budget": config.get("max_evaluations" if is_avo else "max_steps"),
                     "candidate": candidate or None, "modified": activity * 1000,
                     "can_continue": not is_avo and result.get("reason") == "step_budget_exhausted" and not solved,
                     "href": f"/experiments/avo-lab.html?run={quote(run_id, safe='')}" if is_avo else f"/runs/detail.html?run={quote(run_id, safe='')}",
                     "config": config if not is_avo else {"player": config.get("player"), "optimizer_model": config.get("optimizer_model")}})
    # Queued children have no artifacts yet, but still belong in their batch.
    present = {r["id"] for r in rows}
    for run_id, (job_id, row, fresh) in owners.items():
        if run_id not in present:
            public_row = {k: v for k, v in row.items() if k not in {"command", "output"}}
            rows.append({**public_row, "batch": job_id, "modified": 0, "status": row.get("status", "queued") if fresh or row.get("status") in {"cancelled", "failed", "completed"} else "unconfirmed", "status_source": "Batch worker", "solved": False,
                         "log_href": f"/api/workbench/experiments/log?job={quote(job_id, safe='')}&run={quote(Path(row.get('output', '')).name)}"})
    rows.sort(key=lambda r: (r["status"] == "running", r.get("modified", 0)), reverse=True)
    return {"runs": rows, "jobs": jobs, "warnings": warnings, "checked_at": time.time()}
