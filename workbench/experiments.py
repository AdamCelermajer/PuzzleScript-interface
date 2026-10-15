"""Workbench launch plans and artifact APIs for maintained experiment runners."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from workbench.catalog import (ROOT, last_record, legacy_enqueue_backend, normalized_spec, read_json, read_run_spec,
                               run_path, snapshot)


class ExperimentRequest(BaseModel):
    kind: Literal["avo", "codex"]
    # Harness ladder: codex = H2 (Codex SDK), tools = H1 (OpenRouter native tools), raw = H0 (text only).
    agent_backend: Literal["codex", "tools", "raw"] = "codex"
    # Pinned OpenRouter provider slug for every OpenRouter agent; empty keeps OpenRouter routing.
    provider: str = Field(default="", pattern=r"^[a-z0-9][a-z0-9._/-]{0,63}$|^$")
    comparison: bool = False
    game_ids: list[str] = Field(min_length=1, max_length=30)
    models: list[str] = Field(default_factory=lambda: ["gpt-5.6-sol"], min_length=1, max_length=8)
    efforts: list[Literal["minimal", "low", "medium", "high", "xhigh", "max"]] = Field(default_factory=lambda: ["low"], min_length=1, max_length=6)
    conditions: list[Literal["baseline", "baseline-plus"]] = Field(default_factory=lambda: ["baseline-plus"], min_length=1, max_length=2)
    world_model_modes: list[Literal["final-only", "between-hypotheses"]] = Field(default_factory=lambda: ["final-only"], min_length=1, max_length=2)
    optimizer_model: str = "gpt-6-astra"
    optimizer_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    trace_detail: Literal["compact", "full"] = "compact"
    optimizer_service_tier: Literal["", "priority"] = ""
    service_tier: Literal["", "priority"] = ""
    backend_url: str = "http://localhost:8000"
    repeats: int = Field(default=1, ge=1, le=20)
    parallel: int = Field(default=1, ge=1, le=6)
    max_steps: int = Field(default=100, ge=1, le=10000)
    max_evaluations: int = Field(default=10, ge=1, le=100)
    research_moves: int = Field(default=300, ge=1, le=10000)
    solver_moves: int = Field(default=1500, ge=1, le=20000)
    max_hours: float = Field(default=4, ge=0, le=24, description="Wall limit in hours; zero disables the scheduled cutoff")
    continue_from: str = ""

    @field_validator("game_ids", "models")
    @classmethod
    def safe_names(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,159}", v) for v in values):
            raise ValueError("Invalid game or model name")
        return list(dict.fromkeys(values))

    @field_validator("optimizer_model")
    @classmethod
    def safe_model(cls, value: str) -> str:
        return cls.safe_names([value])[0]

    @field_validator("backend_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        from urllib.parse import urlparse
        url = urlparse(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Use an HTTP backend URL without credentials, query or fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_size(self):
        if "ps_enqueue-v1" in self.game_ids:
            if len(self.game_ids) != 1:
                raise ValueError("Enqueue uses its dedicated engine backend; launch it separately from other games")
            from urllib.parse import urlparse
            backend = urlparse(self.backend_url)
            if backend.port == 8000 and backend.hostname in {"localhost", "127.0.0.1", "host.docker.internal"}:
                raise ValueError("Enqueue requires the dedicated backend on port 8001; start scripts/start-enqueue-backend.ps1 first")
        if self.comparison:
            if self.kind != "avo":
                raise ValueError("Matched world-model comparisons are available for AVO only")
            self.world_model_modes = ["final-only", "between-hypotheses"]
            if self.parallel not in {2, 4, 6}:
                raise ValueError("Comparisons need 2, 4 or 6 parallel slots so each pair starts together")
        from avo.client.model_provider import resolve_model
        for model in [*self.models, self.optimizer_model]:
            resolve_model(model)
        agents = [*self.models, *([self.optimizer_model] if self.kind == "avo" else [])]
        if self.provider and any(resolve_model(m)[0] == "nanogpt" for m in agents):
            raise ValueError("Provider pinning is only supported for OpenRouter")
        if self.agent_backend != "codex":
            if any(resolve_model(m)[0] not in {"openrouter", "nanogpt"} for m in agents):
                raise ValueError("The tools and raw harnesses run on OpenRouter or NanoGPT; use provider-qualified model IDs")
        if self.service_tier and any(resolve_model(m)[0] in {"openrouter", "nanogpt"} for m in self.models):
            raise ValueError("OpenRouter and NanoGPT players do not support the Codex service tier setting")
        count = len(self.game_ids) * len(self.models) * len(self.efforts) * self.repeats
        if self.kind == "codex":
            count *= len(self.conditions)
        else:
            count *= len(self.world_model_modes)
        if count > 120:
            raise ValueError("A batch can contain at most 120 runs")
        if self.kind == "avo" and self.continue_from:
            raise ValueError("Saved AVO continuation stays in the explicit campaign recovery workflow")
        if self.continue_from and count != 1:
            raise ValueError("A continuation must be one run")
        return self


class ResumeRequest(BaseModel):
    service_tier: Literal["", "priority"] = ""
    optimizer_service_tier: Literal["", "priority"] = ""


def _avo_recovery_command(saved: dict, output: Path, service_tier: str, optimizer_service_tier: str, trace_detail: str = "compact") -> list[str]:
    player = saved.get("player") or {}
    settings = saved.get("profile_settings") or {}
    command = [sys.executable, "-m", "avo.docker.launch", "--campaign", "--resume-saved-campaign",
               "--game-id", settings["game_id"], "--backend-url", settings["backend_url"],
               "--optimizer-model", saved["optimizer_model"], "--player-model", player["model"],
               "--optimizer-effort", saved.get("optimizer_effort", "low"),
               "--player-effort", player.get("effort", "low"),
               "--trace-detail", trace_detail,
               "--optimizer-service-tier", optimizer_service_tier,
               "--player-service-tier", service_tier,
               "--max-evaluations", str(saved["max_evaluations"]),
               "--world-model-mode", saved.get("world_model_mode", "final-only"),
               "--harness", saved.get("harness", "codex"), "--provider", saved.get("provider", ""),
               "--research-moves", str(player["max_environment_steps"]),
               "--solver-moves", str(saved["fresh_solver_max_environment_steps"]),
               "--max-wall-seconds", str(int(saved["max_wall_seconds"])),
               "--output-dir", str(output)]
    return command


def prepare_avo_recovery(source: Path, target: Path) -> tuple[dict, bool]:
    source_campaign, target_campaign = source / "campaign", target / "campaign"
    saved = read_json(source_campaign / "evolution_config.json")
    lineage = read_json(source_campaign / "lineage.json")
    if not saved or not lineage:
        raise ValueError(f"Saved AVO campaign is incomplete: {source.name}")
    from avo.evolution.candidate import validate_candidate_id
    candidate_ids = [validate_candidate_id(item["candidate_id"])
                     for item in lineage.get("candidates", []) if isinstance(item, dict)]
    if any(path.is_symlink() for path in source_campaign.rglob("*")):
        raise ValueError("Saved campaign contains a symlink")
    shutil.copytree(source_campaign, target_campaign)
    evaluated = {item.get("candidate_id") for item in lineage.get("evaluations", []) if isinstance(item, dict)}
    summary = read_json(source_campaign / "evolution_summary.json")
    needs_report = saved.get("world_model_mode", "off") != "off"
    report = source_campaign / "world_model.md"
    report_present = report.is_file() and bool(report.read_text(encoding="utf-8").strip())
    complete = (bool(summary) or len(evaluated) >= int(saved["max_evaluations"])) and (
        not needs_report or report_present
    )
    if not complete:
        # The original run keeps its failed session for inspection. The new
        # optimizer must record a separate trace, not append to that session.
        shutil.rmtree(target_campaign / "optimizer_analysis", ignore_errors=True)
        for name in ("error.json", "world_model.json", "world_model.md"):
            (target_campaign / name).unlink(missing_ok=True)
        # Retain the registered candidate and immutable seed, but discard only
        # interrupted runtime evidence in the recovery copy so retry is clean.
        target_root = target_campaign.resolve()
        for candidate_id in candidate_ids:
            if candidate_id in evaluated:
                continue
            candidate = target_campaign / candidate_id
            if candidate.resolve().parent != target_root:
                raise ValueError("Candidate recovery path is outside its campaign")
            for name in ("research", "evaluation", "solver"):
                shutil.rmtree(candidate / name, ignore_errors=True)
            for name in ("summary.json", "error.json"):
                (candidate / name).unlink(missing_ok=True)
    return saved, complete


def plan_runs(config: ExperimentRequest, directory: Path, root: Path = ROOT) -> list[dict]:
    from itertools import product
    parent = None
    if config.continue_from:
        parent = run_path(config.continue_from, root)
        from studies.codex_agent.continuation import load_parent
        load_parent(parent)
        saved = read_json(parent / "run_config.json")
        expected = {"game_id": config.game_ids[0], "model": config.models[0], "reasoning_effort": config.efforts[0], "condition": config.conditions[0]}
        if saved.get("harness", "codex") != config.agent_backend or saved.get("provider", "") != config.provider:
            raise ValueError("Continuation must retain the parent harness and provider")
        if any(saved.get(key) != value for key, value in expected.items()):
            raise ValueError("Continuation must retain the parent game, model, effort and condition")
    conditions = config.conditions if config.kind == "codex" else config.world_model_modes
    rows = []
    pairs = {}
    for index, (game, model, effort, repeat, condition) in enumerate(product(config.game_ids, config.models, config.efforts, range(config.repeats), conditions), 1):
        pair_key = (game, model, effort, repeat)
        pairs.setdefault(pair_key, f"pair-{len(pairs)+1:04d}")
        output = directory / f"run-{index:04d}"
        command = [sys.executable, "-m"]
        if config.kind == "avo":
            command += ["avo.docker.launch", "--campaign", "--game-id", game, "--backend-url", config.backend_url,
                        "--optimizer-model", config.optimizer_model, "--player-model", model,
                        "--optimizer-effort", config.optimizer_effort, "--player-effort", effort,
                        "--trace-detail", config.trace_detail,
                        "--optimizer-service-tier", config.optimizer_service_tier,
                        "--player-service-tier", config.service_tier, "--max-evaluations", str(config.max_evaluations),
                        "--world-model-mode", condition, "--harness", config.agent_backend, "--provider", config.provider,
                        "--research-moves", str(config.research_moves), "--solver-moves", str(config.solver_moves),
                        "--max-wall-seconds", str(int(config.max_hours * 3600)), "--output-dir", str(output)]
            artifact = output / "campaign"
        else:
            command += ["studies.codex_agent.run", "--no-window", "--game-id", game,
                        "--backend-url", config.backend_url, "--model", model, "--effort", effort,
                        "--condition", condition, "--harness", config.agent_backend, "--provider", config.provider,
                        "--max-steps", str(config.max_steps), "--output-dir", str(output)]
            if parent:
                command += ["--continue-from", str(parent)]
            artifact = output
        rows.append({"id": artifact.relative_to(root).as_posix(), "kind": config.kind, "game_id": game,
                     "agent_backend": config.agent_backend, "provider": config.provider or None,
                     "pair_id": pairs[pair_key] if config.comparison else None,
                     "model_provider": model.split("/", 1)[0] if model.startswith(("openrouter/", "nanogpt/")) else "openai",
                     "optimizer_model": config.optimizer_model if config.kind == "avo" else None,
                     "model": model, "effort": effort, "condition": condition if config.kind == "codex" else None,
                     "world_model_mode": condition if config.kind == "avo" else None, "repeat": repeat + 1,
                     "output": str(output), "command": command, "status": "queued"})
    return rows


def write_json(path: Path, value: dict) -> None:
    # A separate staging file prevents concurrent saves from replacing each
    # other's payload. Windows readers and sync tools can briefly deny replace.
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    try:
        for attempt in range(40):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(.25)
    finally:
        temporary.unlink(missing_ok=True)


AGENT_EVENT_FIELDS = ("schema", "t", "session", "role", "turn", "type", "text", "output", "exit_code", "tool",
                      "usage", "harness", "model")


def agent_events_path(path: Path) -> Path | None:
    return next((p for p in (path / "agent_events.jsonl", path / "analysis/agent_events.jsonl") if p.is_file()), None)


def read_agent_events(path: Path, limit: int) -> dict:
    """Tail of a normalized `agent-event-v1` log; malformed lines are counted, not fatal."""
    from collections import deque
    events, total, invalid = deque(maxlen=limit or None), 0, 0
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                invalid += 1
                continue
            if not isinstance(item, dict) or not item.get("type"):
                invalid += 1
                continue
            total += 1
            if limit:
                event = {key: item.get(key) for key in AGENT_EVENT_FIELDS}
                event["schema"] = event["schema"] or "agent-event-v1"
                for key in ("text", "output"):
                    if isinstance(event[key], str) and len(event[key]) > 16000:
                        event[key] = event[key][:16000] + "\n[truncated]"
                events.append(event)
    return {"total": total, "invalid_lines": invalid, "truncated": total > len(events), "events": list(events)}


def create_router(root: Path = ROOT, legacy_start=None) -> APIRouter:
    """`legacy_start` serves the historical rule-agent `POST /runs` body (no `modes` key)."""
    router = APIRouter(prefix="/api/workbench")
    cache: dict = {}
    resume_run_lock = threading.Lock()

    @router.get("/model-catalog")
    def models(provider: Literal["openrouter", "nanogpt"] = "openrouter"):
        from workbench.model_catalog import catalog as model_catalog
        try:
            return model_catalog(provider)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.get("/comparison")
    def get_comparison(job: str = Query(...)):
        from workbench.comparisons import comparison
        try:
            return comparison(job, root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    catalog_lock = threading.Lock()

    def build_catalog(token: object) -> bytes:
        data = snapshot(root)
        # Do not expose saved process commands through the public listing.
        public = {**data, "jobs": [{**job, "runs": [{k: v for k, v in row.items() if k not in {"command", "output"}} for row in job["runs"]]} for job in data["jobs"]]}
        body = json.dumps(public, allow_nan=False, default=str).encode()
        # A launch/stop clears the cache (and its token); an older rebuild must not repopulate it.
        if token is not None and cache.get("token") is token:
            cache.update(body=body, data=public, at=time.monotonic())
        return body

    def refresh_in_background(token: object) -> None:
        try:
            build_catalog(token)
        except Exception:  # Keep serving the previous snapshot; the next request retries.
            pass
        finally:
            catalog_lock.release()

    @router.get("/catalog")
    def catalog():
        # Stale-while-revalidate: pollers get the last snapshot at once while one
        # background rebuild (filesystem walk + Docker probe) refreshes it.
        body = cache.get("body")
        if body is None:
            with catalog_lock:
                body = cache.get("body") or build_catalog(cache.setdefault("token", object()))
        elif time.monotonic() - cache.get("at", 0) > 2 and catalog_lock.acquire(blocking=False):
            threading.Thread(target=refresh_in_background, args=(cache.get("token"),), daemon=True).start()
        return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})

    def catalog_runs() -> list[dict]:
        """In-process catalog for the AVO console (shares the cache above)."""
        catalog()
        data = cache.get("data")
        return (data if data is not None else json.loads(build_catalog(None)))["runs"]

    from workbench.avo_console import add_routes as add_avo_routes
    add_avo_routes(router, root, catalog_runs)

    # ---- unified harness runs (revamp contract §4)
    from workbench import runs as harness_runs

    def run_error(exc: Exception) -> HTTPException:
        return HTTPException(409 if isinstance(exc, harness_runs.Conflict) else 400, str(exc))

    def run_request(payload: dict):
        try:
            return harness_runs.RunRequest.model_validate(payload)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_url=False, include_context=False)) from exc

    @router.get("/harnesses")
    def harnesses(catalogs: bool = True):
        from workbench.harness_catalog import harness_listing
        return harness_listing(root, include_public_catalogs=catalogs)

    @router.post("/runs/preview")
    def preview_runs(payload: dict = Body(...)):
        config = run_request(payload)
        try:
            rows, warnings = harness_runs.plan_matrix(config, root / "output/workbench/preview", root)
        except (ValueError, OSError) as exc:
            raise run_error(exc) from exc
        public = ("mode", "harness", "model", "optimizer_model", "effort", "optimizer_effort", "game_id",
                  "world_model_mode", "repeat", "match_id", "backend_url", "budget", "command")
        return {"runs": [{k: row[k] for k in public} for row in rows], "warnings": warnings, "count": len(rows),
                "parallel": min(config.parallel, len(rows))}

    @router.post("/runs", status_code=202)
    def launch_runs(payload: dict = Body(...)):
        if "modes" not in payload and legacy_start is not None:
            return legacy_start(payload)
        config = run_request(payload)
        try:
            launched = harness_runs.launch_matrix(config, root)
        except (ValueError, OSError) as exc:
            raise run_error(exc) from exc
        cache.clear()
        return launched

    class RunResumeRequest(BaseModel):
        run_id: str = Field(min_length=1, max_length=400)

    @router.post("/runs/resume", status_code=202)
    def resume_harness_run(request: RunResumeRequest):
        with resume_run_lock:
            try:
                resumed = harness_runs.resume_runs([request.run_id], root)
            except (ValueError, OSError, KeyError) as exc:
                raise run_error(exc) from exc
        cache.clear()
        return resumed

    @router.post("/experiments/preview")
    def preview(config: ExperimentRequest):
        try:
            rows = plan_runs(config, root / "output/workbench/preview", root)
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"count": len(rows), "parallel": min(config.parallel, len(rows)), "max_hours": config.max_hours,
                "comparison": config.comparison,
                "campaigns": [{k: row[k] for k in ("game_id", "pair_id", "agent_backend", "model_provider", "model", "optimizer_model", "effort", "condition", "world_model_mode", "repeat")} for row in rows],
                "commands": [row["command"] for row in rows]}

    @router.post("/experiments", status_code=202)
    def launch(config: ExperimentRequest):
        directory = root / "output/workbench" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
        try:
            rows = plan_runs(config, directory, root)
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc
        directory.mkdir(parents=True, exist_ok=False)
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "heartbeat": time.time(),
                    "status": "starting", "config": config.model_dump(), "runs": rows}
        write_json(directory / "job.json", manifest)
        try:
            with (directory / "worker.log").open("wb") as log:
                subprocess.Popen([sys.executable, "-m", "workbench.experiment_job", str(directory)], cwd=root,
                                 stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            manifest.update(status="failed", error=str(exc))
            write_json(directory / "job.json", manifest)
            raise HTTPException(503, "Could not start the experiment worker") from exc
        cache.clear()
        return {"id": directory.relative_to(root).as_posix(), "count": len(rows)}

    @router.post("/experiments/stop", status_code=202)
    def stop(job: str = Query(...)):
        try:
            path = run_path(job, root)
            if path.parent != root / "output/workbench" or not (path / "job.json").is_file():
                raise ValueError("Only workbench-owned batches can be stopped here")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        (path / "stop.request").touch()
        return {"stop_requested": True}

    @router.post("/experiments/pause", status_code=202)
    def pause(job: str = Query(...)):
        try:
            path = run_path(job, root)
            manifest = read_json(path / "job.json")
            if path.parent != root / "output/workbench" or manifest.get("config", {}).get("kind") not in {"avo", "matrix"}:
                raise ValueError("Only active workbench-owned AVO or harness batches can be paused here")
            if manifest.get("status") not in {"starting", "running"}:
                raise ValueError("Only an active batch can be paused")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        (path / "pause.request").touch()
        return {"pause_requested": True}

    @router.post("/experiments/dismiss")
    def dismiss(job: str = Query(...)):
        try:
            path = run_path(job, root)
            manifest = read_json(path / "job.json")
            if path.parent != root / "output/workbench" or manifest.get("config", {}).get("kind") not in {"avo", "matrix"}:
                raise ValueError("Only workbench-owned AVO or harness batches can be removed from Runs")
            if manifest.get("status") not in {"paused", "cancelled", "failed"} or manifest.get("resumed_as"):
                raise ValueError("Only an inactive resumable batch can be removed from Runs")
            manifest["dismissed_from_runs_at"] = datetime.now(timezone.utc).isoformat()
            write_json(path / "job.json", manifest)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        cache.clear()
        return {"dismissed_from_runs": True}

    @router.post("/experiments/resume", status_code=202)
    def resume(config: ResumeRequest, job: str = Query(...)):
        try:
            source = run_path(job, root)
            manifest = read_json(source / "job.json")
            if source.parent != root / "output/workbench" or manifest.get("config", {}).get("kind") != "avo":
                raise ValueError("Only workbench-owned AVO batches can be resumed here")
            if manifest.get("status") not in {"paused", "cancelled", "failed"}:
                raise ValueError("Only a paused, cancelled, or failed AVO batch can be resumed")
            if manifest.get("resumed_as"):
                raise ValueError(f"This batch was already resumed as {manifest['resumed_as']}")
            if any(read_json(Path(row["output"]) / "campaign/error.json").get("status") == "needs_assistance"
                   for row in manifest.get("runs", [])):
                raise ValueError("Backend needs assistance; inspect the error and start a new campaign after repair")
            if any(legacy_enqueue_backend(read_json(Path(row["output"]) / "campaign/evolution_config.json"))
                   for row in manifest.get("runs", [])):
                raise ValueError("Legacy Enqueue engine cannot be resumed; start a new campaign on port 8001")
            directory = root / "output/workbench" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-resume-" + uuid4().hex[:8])
            directory.mkdir(parents=True, exist_ok=False)
            rows = []
            for index, old in enumerate(manifest.get("runs", []), 1):
                old_output = Path(old["output"]).resolve()
                if not old_output.is_relative_to(source.resolve()):
                    raise ValueError("Saved campaign output is outside its batch")
                if read_json(old_output / "recovery.json").get("resumed_as"):
                    continue
                output = directory / f"run-{index:04d}"
                saved, complete = prepare_avo_recovery(old_output, output)
                artifact = output / "campaign"
                rows.append({**{k: v for k, v in old.items() if k not in {"id", "output", "command", "pid", "started_at", "returncode"}},
                             "id": artifact.relative_to(root).as_posix(), "output": str(output),
                             "command": _avo_recovery_command(saved, output, config.service_tier, config.optimizer_service_tier,
                                                               manifest["config"].get("trace_detail", "compact")),
                             "status": "completed" if complete else "queued"})
            if not rows:
                raise ValueError("Every run in this batch already has a separate recovery")
            recovery_config = {**manifest["config"], "service_tier": config.service_tier,
                               "optimizer_service_tier": config.optimizer_service_tier}
            recovery = {"created_at": datetime.now(timezone.utc).isoformat(), "heartbeat": time.time(),
                        "status": "starting", "config": recovery_config, "runs": rows,
                        "recovery_of": job}
            write_json(directory / "job.json", recovery)
            with (directory / "worker.log").open("wb") as log:
                subprocess.Popen([sys.executable, "-m", "workbench.experiment_job", str(directory)], cwd=root,
                                 stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            recovery_id = directory.relative_to(root).as_posix()
            manifest["resumed_as"] = recovery_id
            write_json(source / "job.json", manifest)
        except (ValueError, OSError, KeyError) as exc:
            if 'directory' in locals() and directory.is_dir() and not (directory / "job.json").is_file():
                shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(400, str(exc)) from exc
        cache.clear()
        return {"id": recovery_id, "count": len(rows)}

    @router.post("/experiments/resume-run", status_code=202)
    def resume_run(config: ResumeRequest, run: str = Query(...)):
        with resume_run_lock:
            try:
                campaign = run_path(run, root)
                old_output = campaign.parent
                source_job = old_output.parent
                if (campaign.name != "campaign" or source_job.parent != root / "output/workbench"
                        or not (source_job / "job.json").is_file()):
                    raise ValueError("Only a Workbench-owned AVO run can be resumed")
                manifest = read_json(source_job / "job.json")
                old = next((row for row in manifest.get("runs", []) if row.get("id") == run), None)
                if (manifest.get("config", {}).get("kind") != "avo" or not old
                        or Path(old.get("output", "")).resolve() != old_output.resolve()
                        or old.get("status") != "failed"):
                    raise ValueError("Only a failed Workbench AVO run can be resumed")
                if read_json(old_output / "recovery.json").get("resumed_as"):
                    raise HTTPException(409, "This run already has a recovery")
                if read_json(campaign / "error.json").get("status") == "needs_assistance":
                    raise HTTPException(409, "Backend needs assistance; inspect the error and start a new campaign after repair")
                if legacy_enqueue_backend(read_json(campaign / "evolution_config.json")):
                    raise HTTPException(409, "Legacy Enqueue engine cannot be resumed; start a new campaign on port 8001")
                directory = root / "output/workbench" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-resume-" + uuid4().hex[:8])
                output = directory / "run-0001"
                if not output.resolve().is_relative_to((root / "output/workbench").resolve()):
                    raise ValueError("Recovery output is outside Workbench")
                saved, complete = prepare_avo_recovery(old_output, output)
                if complete:
                    raise ValueError("This campaign already has a final result")
                recovery_id = directory.relative_to(root).as_posix()
                artifact = output / "campaign"
                row = {**{k: v for k, v in old.items() if k not in {"id", "output", "command", "pid", "started_at", "returncode"}},
                       "id": artifact.relative_to(root).as_posix(), "output": str(output),
                       "command": _avo_recovery_command(saved, output, config.service_tier, config.optimizer_service_tier,
                                                        manifest["config"].get("trace_detail", "compact")),
                       "status": "queued", "repeat": 1, "pair_id": None}
                recovery_config = {**manifest["config"], "game_ids": [old["game_id"]], "parallel": 1, "repeats": 1,
                                   "comparison": False, "service_tier": config.service_tier,
                                   "optimizer_service_tier": config.optimizer_service_tier}
                write_json(directory / "job.json", {
                    "created_at": datetime.now(timezone.utc).isoformat(), "heartbeat": time.time(),
                    "status": "starting", "config": recovery_config, "runs": [row], "recovery_of": run,
                })
                marker = old_output / "recovery.json"
                write_json(marker, {"resumed_as": row["id"], "created_at": datetime.now(timezone.utc).isoformat()})
                try:
                    with (directory / "worker.log").open("wb") as log:
                        subprocess.Popen([sys.executable, "-m", "workbench.experiment_job", str(directory)], cwd=root,
                                         stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except OSError:
                    marker.unlink(missing_ok=True)
                    raise
            except HTTPException:
                raise
            except (ValueError, OSError, KeyError) as exc:
                raise HTTPException(400, str(exc)) from exc
            cache.clear()
            return {"id": recovery_id, "run": row["id"]}

    @router.get("/submission")
    def get_submission(run: str = Query(...), candidate: str = ""):
        from workbench.submissions import submission
        try:
            return submission(run, root, candidate)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/submission/file")
    def get_submission_file(run: str = Query(...), file: str = Query(...), download: bool = False):
        from workbench.submissions import submission_file
        try:
            target = submission_file(run, file, root)
            if download:
                return FileResponse(target, filename=target.name)
            if target.stat().st_size > 2_000_000:
                raise HTTPException(413, "File is too large to preview; use Download")
            return Response(target.read_text(encoding="utf-8", errors="replace"), media_type="text/plain",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/submission/download")
    def download_submission(run: str = Query(...), candidate: str = ""):
        import io
        import zipfile
        from workbench.submissions import submission, submission_file
        try:
            record = submission(run, root, candidate)
            if not record["solver_present"]:
                raise HTTPException(404, "No evaluated solver.py is available")
            if sum(f["size"] for f in record["files"]) > 128_000_000:
                raise HTTPException(413, "Submission exceeds the 128 MB download limit")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in record["files"]:
                    # Preserve the evaluated directory intact, including relative helper paths.
                    archive.write(submission_file(run, item["path"], root), "solver/" + item["name"])
                if record["world_model"]:
                    archive.write(submission_file(run, "world_model.md", root), "world_model.md")
                archive.writestr("submission_record.json", json.dumps(record, indent=2))
            return Response(buffer.getvalue(), media_type="application/zip",
                            headers={"Content-Disposition": 'attachment; filename="avo-submission.zip"'})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/record")
    def record(run: str = Query(...)):
        try:
            path = run_path(run, root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not (path / "run_config.json").is_file():
            raise HTTPException(404, "Direct-player run not found")
        names = ["run_config.json", "result.json", "error.json", "restoration.json", "transitions.jsonl", "transcript.jsonl", "codex_session.jsonl", "model_session.jsonl", "isolation_manifest.json"]
        notes = []
        for note in (path / "workspace").glob("*.md"):
            if not note.is_symlink():
                notes.append(note.relative_to(path).as_posix())
        return {"id": run, "config": read_json(path / "run_config.json"), "result": read_json(path / "result.json"),
                "error": read_json(path / "error.json"), "latest_transition": last_record(path / "transitions.jsonl"),
                "files": [name for name in names + notes if (path / name).is_file()]}

    @router.get("/experiments/log")
    def job_log(job: str = Query(...), run: str = Query(...)):
        try:
            path = run_path(job, root)
            if path.parent != root / "output/workbench" or not re.fullmatch(r"run-\d{4}", run):
                raise ValueError("Invalid workbench log")
            target = run_path(job + "/" + run + ".log", root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            with target.open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - 128000))
                text = stream.read().decode("utf-8", errors="replace")
            if size > 128000:
                text = "[Showing the last 128 KB]\n" + text
            return Response(text, media_type="text/plain", headers={"Cache-Control": "no-store"})
        except OSError as exc:
            raise HTTPException(404, "No child log yet") from exc

    @router.get("/record/timeline")
    def timeline(run: str = Query(...), index: int = Query(..., ge=1, le=100000)):
        try:
            path = run_path(run, root)
            with (path / "transitions.jsonl").open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                        if item.get("action_index") == index:
                            return {"transition": item}
                    except (ValueError, AttributeError):
                        continue
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError:
            pass
        raise HTTPException(404, "Transition not found")

    @router.get("/record/file")
    def record_file(run: str = Query(...), file: str = Query(...)):
        try:
            path = run_path(run, root)
            target = run_path(run + "/" + file, root)
            allowed = {"run_config.json", "result.json", "error.json", "restoration.json", "transitions.jsonl", "transcript.jsonl", "codex_session.jsonl", "model_session.jsonl", "isolation_manifest.json"}
            note = len(Path(file).parts) == 2 and Path(file).parts[0] == "workspace" and target.suffix == ".md"
            frame = re.fullmatch(r"frames/[0-9]{3,}\.png", file) is not None
            if not target.is_relative_to(path) or not (file in allowed or note or frame):
                raise ValueError("Invalid artifact")
            if any(p.startswith(".") for p in Path(file).parts) or "model_requests" in Path(file).parts:
                raise ValueError("Artifact is not available here")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not target.is_file():
            raise HTTPException(404, "Artifact not found")
        if frame:
            return FileResponse(target, media_type="image/png")
        return FileResponse(target, filename=target.name)

    return router
