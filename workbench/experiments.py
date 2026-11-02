"""Workbench API: the run catalog, launching, stopping and resuming runs, pins. One run's files are
served by record_routes.py, its recorded model calls and Prompt build by calls_routes.py."""
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
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from workbench.catalog import ROOT, STOPPED_RUNS, job_run_name, read_json, run_path, snapshot


def resolve_model(model: str) -> tuple[str, str]:
    """Provider and native ID; mirrors harnesses.model_provider without importing harnesses."""
    for provider in ("nanogpt", "openrouter"):
        if model.startswith(provider + "/"):
            native = model.removeprefix(provider + "/")
            if not native or any(not part for part in native.split("/")) or (provider == "openrouter" and "/" not in native):
                raise ValueError("Use openrouter/vendor/model for OpenRouter models" if provider == "openrouter"
                                 else "Use nanogpt/model with a model ID from the NanoGPT catalog")
            return provider, native
    if model.startswith("opencode/"):
        raise ValueError("OpenCode is retired; use a Codex model or openrouter/vendor/model")
    return "openai", model


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


class RunResumeRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=400)


class ResumeRequest(BaseModel):
    service_tier: Literal["", "priority"] = ""
    optimizer_service_tier: Literal["", "priority"] = ""


CANDIDATE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")


def validate_candidate_id(candidate_id: str) -> str:
    """Same rule as frameworks.avo.evolution.candidate, without importing the avo package."""
    value = str(candidate_id).strip()
    if not CANDIDATE_ID.fullmatch(value):
        raise ValueError("candidate_id must be a safe 1-80 character identifier")
    return value


def prepare_avo_recovery(source: Path, target: Path) -> tuple[dict, bool]:
    source_campaign, target_campaign = source / "campaign", target / "campaign"
    saved = read_json(source_campaign / "evolution_config.json")
    lineage = read_json(source_campaign / "lineage.json")
    if not saved or not lineage:
        raise ValueError(f"Saved AVO campaign is incomplete: {source.name}")
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
        from frameworks.baseline.continuation import load_parent
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
            command += ["frameworks.baseline.run", "--game-id", game,
                        "--backend-url", config.backend_url, "--model", model, "--effort", effort,
                        "--harness", config.agent_backend, "--provider", config.provider,
                        "--max-steps", str(config.max_steps), "--output-dir", str(output)]
            if condition == "baseline-plus":
                command.append("--notes")
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


def create_router(root: Path = ROOT) -> APIRouter:
    router = APIRouter(prefix="/api/workbench")
    cache: dict = {}
    resume_run_lock = threading.Lock()
    stop_run_lock = threading.Lock()

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
    from workbench.calls_routes import add_routes as add_calls_routes
    from workbench.record_routes import add_routes as add_record_routes
    add_avo_routes(router, root, catalog_runs)
    add_record_routes(router, root)
    add_calls_routes(router, root, catalog_runs)

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

    @router.post("/runs/archive")
    def archive_runs(payload: dict = Body(...)):
        from workbench.catalog import set_archived
        runs, archived = payload.get("runs"), payload.get("archived", True)
        if not isinstance(runs, list) or not runs or not all(isinstance(r, str) for r in runs) or not isinstance(archived, bool):
            raise HTTPException(400, "Expected {runs: [run ids], archived: bool}")
        try:
            current = set_archived(runs, archived, root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        cache.clear()
        return {"archived": sorted(current)}

    @router.get("/pins")
    def list_pins(run: str | None = Query(None, max_length=500)):
        from workbench.pins import read_pins
        return {"pins": read_pins(root, run)}

    @router.post("/pins", status_code=201)
    def create_pin(payload: dict = Body(...)):
        from workbench.pins import add_pin
        try:
            return add_pin(root, payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.patch("/pins/{pin_id}")
    def edit_pin(pin_id: str, payload: dict = Body(...)):
        from workbench.pins import update_pin
        try:
            return update_pin(root, pin_id, payload.get("note"))
        except KeyError as exc:
            raise HTTPException(404, "No such pin") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete("/pins/{pin_id}", status_code=204)
    def delete_pin(pin_id: str):
        from workbench.pins import remove_pin
        try:
            remove_pin(root, pin_id)
        except KeyError as exc:
            raise HTTPException(404, "No such pin") from exc
        return Response(status_code=204)

    @router.get("/frameworks")
    def frameworks():
        from frameworks.registry import list_frameworks
        return {"frameworks": list_frameworks()}

    @router.post("/runs/preview")
    def preview_runs(payload: dict = Body(...)):
        config = run_request(payload)
        try:
            rows, warnings = harness_runs.plan_matrix(config, root / "output/workbench/preview", root)
        except (ValueError, OSError) as exc:
            raise run_error(exc) from exc
        public = ("framework", "options", "variant", "harness", "model", "optimizer_model", "effort",
                  "optimizer_effort", "game_id", "repeat", "match_id", "backend_url", "max_wall_seconds", "command")
        return {"runs": [{k: row[k] for k in public} for row in rows], "warnings": warnings, "count": len(rows),
                "parallel": min(config.parallel, len(rows))}

    @router.post("/runs", status_code=202)
    def launch_runs(payload: dict = Body(...)):
        config = run_request(payload)
        try:
            launched = harness_runs.launch_matrix(config, root)
        except (ValueError, OSError) as exc:
            raise run_error(exc) from exc
        cache.clear()
        return launched

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

    @router.post("/experiments/stop-run", status_code=202)
    def stop_run(job: str = Query(...), run: str = Query(...)):
        """Stop one run of a batch; the others go on. The run is recorded as stopped (cancelled), not failed."""
        from workbench.experiment_job import owned_container

        with stop_run_lock:
            try:
                path = run_path(job, root)
                if path.parent != root / "output/workbench" or not (path / "job.json").is_file():
                    raise ValueError("Only runs of workbench-owned batches can be stopped here")
                if not re.fullmatch(r"run-\d{4}", run):
                    raise ValueError("Invalid run")
                row = next((r for r in read_json(path / "job.json").get("runs", []) if job_run_name(r) == run), None)
                if row is None:
                    raise ValueError("This run is not part of the batch")
                if row.get("status") not in {"queued", "starting", "running"}:
                    raise ValueError("Only an active run can be stopped")
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            saved = read_json(path / STOPPED_RUNS).get("runs")
            runs = saved if isinstance(saved, list) else []
            if run not in {r.get("run") for r in runs if isinstance(r, dict)}:
                write_json(path / STOPPED_RUNS, {"runs": [*runs, {"run": run, "at": datetime.now(timezone.utc).isoformat()}]})
        # Same exact ownership as the batch stop: removing this run's own container ends its launcher.
        # The batch worker stops a child without one and never starts a stopped queued run.
        container = owned_container(row) if row.get("status") == "running" else ""
        if container:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=20)
        cache.clear()
        return {"stop_requested": True, "container_removed": bool(container)}

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

    # Former recovery routes are thin aliases of the unified resume (harnesses.launch
    # `--resume` / `--continue-from`). Service tiers no longer exist; the body is ignored.
    @router.post("/experiments/resume", status_code=202)
    def resume(config: ResumeRequest | None = None, job: str = Query(...)):
        with resume_run_lock:
            try:
                source = run_path(job, root)
                manifest = read_json(source / "job.json")
                if source.parent != root / "output/workbench" or manifest.get("config", {}).get("kind") not in {"avo", "matrix"}:
                    raise ValueError("Only workbench-owned AVO or harness batches can be resumed here")
                if manifest.get("status") not in {"paused", "cancelled", "failed"}:
                    raise ValueError("Only a paused, cancelled, or failed batch can be resumed")
                if manifest.get("resumed_as"):
                    raise ValueError(f"This batch was already resumed as {manifest['resumed_as']}")
                resumed = harness_runs.resume_runs([row["id"] for row in manifest.get("runs", []) if row.get("id")],
                                                   root, recovery_of=job, skip_unavailable=True)
                manifest["resumed_as"] = resumed["job_id"]
                write_json(source / "job.json", manifest)
            except (ValueError, OSError, KeyError) as exc:
                raise run_error(exc) from exc
        cache.clear()
        return resumed

    @router.post("/experiments/resume-run", status_code=202)
    def resume_run(config: ResumeRequest | None = None, run: str = Query(...)):
        with resume_run_lock:
            try:
                resumed = harness_runs.resume_runs([run], root)
            except (ValueError, OSError, KeyError) as exc:
                raise run_error(exc) from exc
        cache.clear()
        return resumed

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

    return router
