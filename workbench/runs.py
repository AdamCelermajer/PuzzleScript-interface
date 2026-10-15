"""Unified run matrix, launch and resume for `python -m harnesses.launch` (revamp contract §2-4)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from workbench.catalog import (HARNESS_IDS, ROOT, legacy_enqueue_backend, live_containers, normalized_spec,
                               read_json, run_path)
from workbench.harness_catalog import model_error, model_provider

Mode = Literal["baseline", "baseline-plus", "campaign"]
Harness = Literal["codex", "claude-code", "opencode", "antigravity", "bare"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
WorldModelMode = Literal["final-only", "between-hypotheses"]

LAUNCH = ["uv", "run", "python", "-m", "harnesses.launch"]
DEFAULT_BACKEND_URL = "http://host.docker.internal:8000"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}
ENQUEUE_GAME = "ps_enqueue-v1"
ENQUEUE_PORT = 8001
MAX_RUNS = 120
ACTIVE = {"queued", "starting", "running", "stopping"}
NAME = r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,159}"


class Conflict(ValueError):
    """The request is valid but the run's current state forbids it (HTTP 409)."""


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_wall_seconds: int = Field(default=0, ge=0, le=30 * 86400, description="0 = unlimited")
    max_steps: int = Field(default=200, ge=1, le=10000)
    max_evaluations: int = Field(default=8, ge=1, le=100)
    research_moves: int = Field(default=400, ge=1, le=10000)
    solver_moves: int = Field(default=400, ge=1, le=20000)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modes: list[Mode] = Field(min_length=1, max_length=3)
    harnesses: list[Harness] = Field(min_length=1, max_length=5)
    models: list[str] = Field(min_length=1, max_length=12)
    optimizer_model: str | None = None
    optimizer_effort: Effort | None = None
    efforts: list[Effort] = Field(default_factory=lambda: ["medium"], min_length=1, max_length=5)
    games: list[str] = Field(min_length=1, max_length=30)
    repeats: int = Field(default=1, ge=1, le=20)
    parallel: int = Field(default=1, ge=1, le=6)
    budget: Budget = Field(default_factory=Budget)
    world_model_modes: list[WorldModelMode] = Field(default_factory=lambda: ["final-only"], min_length=1, max_length=2)
    provider: str = Field(default="", pattern=r"^[a-z0-9][a-z0-9._/-]{0,63}$|^$")
    label: str = Field(default="", max_length=80)
    backend_url: str | None = None

    @field_validator("games", "models")
    @classmethod
    def safe_names(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(NAME, v) for v in values):
            raise ValueError("Invalid game or model name")
        return list(dict.fromkeys(values))

    @field_validator("modes", "harnesses", "efforts", "world_model_modes")
    @classmethod
    def unique(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("optimizer_model")
    @classmethod
    def safe_model(cls, value: str | None) -> str | None:
        return cls.safe_names([value])[0] if value else None

    @field_validator("backend_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        return clean_url(value) if value else None


def clean_url(value: str) -> str:
    url = urlparse(value)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Use an HTTP backend URL without credentials, query or fragment")
    return value.rstrip("/")


def default_backend_url() -> str:
    """One setting for every harness: all of them run inside Docker."""
    return clean_url(os.environ.get("WORKBENCH_BACKEND_URL") or DEFAULT_BACKEND_URL)


def game_backend(game: str, backend_url: str) -> str:
    """Enqueue needs the `PUZZLESCRIPT_METHOD=ondemand` engine, which only the
    dedicated runtime (scripts/start-enqueue-backend.ps1, ARC port 8001) runs."""
    url = urlparse(backend_url)
    if game == ENQUEUE_GAME and url.hostname in LOCAL_HOSTS and (url.port or 80) != ENQUEUE_PORT:
        return urlunparse(url._replace(netloc=f"{url.hostname}:{ENQUEUE_PORT}"))
    return backend_url


def launch_command(*, mode: str, harness: str, model: str, effort: str, game_id: str, backend_url: str,
                   output: Path, budget: dict, optimizer_model: str | None = None,
                   optimizer_effort: str | None = None, world_model_mode: str | None = None, provider: str = "",
                   resume: bool = False, continue_from: Path | None = None) -> list[str]:
    command = [*LAUNCH, "--mode", mode, "--harness", harness, "--model", model, "--effort", effort,
               "--game-id", game_id, "--backend-url", backend_url, "--output-dir", str(output),
               "--max-wall-seconds", str(int(budget.get("max_wall_seconds") or 0))]
    if mode == "campaign":
        command += ["--optimizer-model", optimizer_model or model, "--optimizer-effort", optimizer_effort or effort,
                    "--max-evaluations", str(budget["max_evaluations"]), "--research-moves", str(budget["research_moves"]),
                    "--solver-moves", str(budget["solver_moves"]), "--world-model-mode", world_model_mode or "final-only"]
    else:
        command += ["--max-steps", str(budget["max_steps"])]
    if provider:
        command += ["--provider", provider]
    if resume:
        command.append("--resume")
    if continue_from is not None:
        command += ["--continue-from", str(continue_from)]
    return command


def validate_request(config: RunRequest) -> tuple[list[tuple[str, str]], list[str]]:
    """Return the valid (harness, model) pairs plus warnings, or raise ValueError."""
    campaign = "campaign" in config.modes
    baseline = any(mode != "campaign" for mode in config.modes)
    explicit, explicit_budget = config.model_fields_set, config.budget.model_fields_set
    if not campaign:
        for field in ("optimizer_model", "optimizer_effort", "world_model_modes"):
            if field in explicit:
                raise ValueError(f"{field} applies only to campaign mode")
        for field in ("max_evaluations", "research_moves", "solver_moves"):
            if field in explicit_budget:
                raise ValueError(f"budget.{field} applies only to campaign mode")
    if not baseline and "max_steps" in explicit_budget:
        raise ValueError("budget.max_steps applies only to baseline and baseline-plus modes")
    if config.provider:
        if any(h not in {"opencode", "bare"} for h in config.harnesses):
            raise ValueError("Provider pinning applies only to the opencode and bare harnesses")
        if any(model_provider(m) != "openrouter" for m in config.models + ([config.optimizer_model] if config.optimizer_model else [])):
            raise ValueError("Provider pinning is only supported for OpenRouter models")
    pairs, warnings, fitting = [], [], set()
    for harness, model in product(config.harnesses, config.models):
        reason = model_error(harness, model)
        if reason is None:
            pairs.append((harness, model))
            fitting.add(model)
        elif len(config.harnesses) > 1:
            warnings.append(f"Skipped {harness} × {model}: {reason}")
        else:
            raise ValueError(reason)
    unmatched = [m for m in config.models if m not in fitting]
    if unmatched:
        raise ValueError(f"No selected harness runs {', '.join(unmatched)}")
    if campaign and config.optimizer_model:
        for harness in {h for h, _ in pairs}:
            reason = model_error(harness, config.optimizer_model)
            if reason:
                raise ValueError(f"Optimizer model: {reason}")
    return pairs, warnings


def plan_matrix(config: RunRequest, directory: Path, root: Path = ROOT) -> tuple[list[dict], list[str]]:
    pairs, warnings = validate_request(config)
    backend = config.backend_url or default_backend_url()
    budget = config.budget.model_dump()
    rows, matches = [], {}
    combos = []
    for game, mode, (harness, model), effort, repeat in product(config.games, config.modes, pairs, config.efforts,
                                                                range(config.repeats)):
        for world_model_mode in (config.world_model_modes if mode == "campaign" else [None]):
            combos.append((game, mode, harness, model, effort, repeat, world_model_mode))
    if not combos:
        raise ValueError("The selection produces no runs")
    if len(combos) > MAX_RUNS:
        raise ValueError(f"A batch can contain at most {MAX_RUNS} runs (this selection has {len(combos)})")
    enqueue_warned = False
    for index, (game, mode, harness, model, effort, repeat, world_model_mode) in enumerate(combos, 1):
        url = game_backend(game, backend)
        if url != backend and not enqueue_warned:
            enqueue_warned = True
            warnings.append(f"{ENQUEUE_GAME} uses its dedicated ondemand engine at {url}; "
                            "start scripts/start-enqueue-backend.ps1 and keep it running")
        output = directory / f"run-{index:04d}"
        is_campaign = mode == "campaign"
        row_budget = ({k: budget[k] for k in ("max_wall_seconds", "max_evaluations", "research_moves", "solver_moves")}
                      if is_campaign else {k: budget[k] for k in ("max_wall_seconds", "max_steps")})
        optimizer_model = (config.optimizer_model or model) if is_campaign else None
        optimizer_effort = (config.optimizer_effort or effort) if is_campaign else None
        command = launch_command(mode=mode, harness=harness, model=model, effort=effort, game_id=game,
                                 backend_url=url, output=output, budget=row_budget, optimizer_model=optimizer_model,
                                 optimizer_effort=optimizer_effort, world_model_mode=world_model_mode,
                                 provider=config.provider)
        artifact = output / "campaign" if is_campaign else output
        match_id = matches.setdefault((game, harness, model, effort, repeat), f"match-{len(matches) + 1:04d}")
        rows.append({"id": artifact.relative_to(root).as_posix(), "launcher": "harnesses",
                     "kind": "avo" if is_campaign else "codex", "mode": mode, "harness": harness,
                     "agent_backend": harness, "model": model, "model_provider": model_provider(model),
                     "optimizer_model": optimizer_model, "effort": effort, "optimizer_effort": optimizer_effort,
                     "game_id": game, "backend_url": url, "world_model_mode": world_model_mode,
                     "condition": None if is_campaign else mode, "provider": config.provider or None,
                     "repeat": repeat + 1, "match_id": match_id, "pair_id": None, "budget": row_budget,
                     "max_wall_seconds": row_budget["max_wall_seconds"], "output": str(output),
                     "command": command, "status": "queued"})
    return rows, warnings


def write_json(path: Path, value: dict) -> None:
    from workbench.experiments import write_json as atomic_write
    atomic_write(path, value)


def new_job_directory(root: Path, label: str = "") -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40]
    name = datetime.now().strftime("%Y%m%dT%H%M%S") + (f"-{slug}" if slug else "") + "-" + uuid4().hex[:8]
    return root / "output/workbench" / name


def start_job(directory: Path, manifest: dict, root: Path) -> None:
    """Persist the manifest and detach the bounded batch worker."""
    write_json(directory / "job.json", manifest)
    try:
        with (directory / "worker.log").open("wb") as log:
            subprocess.Popen([sys.executable, "-m", "workbench.experiment_job", str(directory)], cwd=root,
                             stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        manifest.update(status="failed", error=str(exc))
        write_json(directory / "job.json", manifest)
        raise


def launch_matrix(config: RunRequest, root: Path = ROOT) -> dict:
    directory = new_job_directory(root, config.label)
    rows, warnings = plan_matrix(config, directory, root)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "heartbeat": time.time(), "status": "starting",
                "config": {"kind": "matrix", "launcher": "harnesses", **config.model_dump(), "comparison": False},
                "warnings": warnings, "runs": rows}
    start_job(directory, manifest, root)
    return {"job_id": directory.relative_to(root).as_posix(), "id": directory.relative_to(root).as_posix(),
            "count": len(rows), "warnings": warnings}


# ---------------------------------------------------------------- resume

def find_owner(run_id: str, root: Path) -> tuple[Path, dict, dict, bool] | None:
    for manifest_path in (root / "output/workbench").glob("*/job.json"):
        manifest = read_json(manifest_path)
        row = next((r for r in manifest.get("runs", []) if r.get("id") == run_id), None)
        if row is not None:
            heartbeat = manifest.get("heartbeat", 0)
            fresh = isinstance(heartbeat, (int, float)) and time.time() - heartbeat < 20
            return manifest_path.parent, manifest, row, fresh
    return None


def plan_resume(run_id: str, output: Path, root: Path = ROOT) -> tuple[dict, Path]:
    """Prepare one resumed run in `output`; returns its manifest row and the
    source marker path. Campaigns copy the saved lineage and pass `--resume`;
    baseline modes replay the parent with `--continue-from`."""
    path = run_path(run_id, root)
    is_avo = (path / "evolution_config.json").is_file()
    config = read_json(path / ("evolution_config.json" if is_avo else "run_config.json"))
    spec = normalized_spec(path, config, is_avo)
    if not config and spec["spec_source"] != "run_spec":
        raise ValueError("Run not found")
    if spec["harness"] not in HARNESS_IDS:
        raise Conflict(f"Runs recorded with the {spec['harness']} harness cannot be resumed")
    if not spec["model"] or not spec["game_id"]:
        raise ValueError("The saved run does not record its model and game")
    owner = find_owner(run_id, root)
    if owner and owner[3] and owner[2].get("status") in ACTIVE:
        raise Conflict("This run is still active in its batch")
    mode = spec["mode"]
    budget = {**{k: v for k, v in Budget().model_dump().items()}, **(spec["budget"] or {})}
    if is_avo or mode == "campaign":
        if path.name != "campaign":
            raise ValueError("Only campaigns saved as <run>/campaign can be resumed")
        if live_containers()[0].get(str(path.parent.resolve()).casefold()):
            raise Conflict("Docker reports this campaign running")
        marker = path.parent / "recovery.json"
        if read_json(marker).get("resumed_as"):
            raise Conflict("This run already has a recovery")
        if read_json(path / "error.json").get("status") == "needs_assistance":
            raise Conflict("Backend needs assistance; inspect the error and start a new campaign after repair")
        if legacy_enqueue_backend(config):
            raise Conflict("Legacy Enqueue engine cannot be resumed; start a new campaign on port 8001")
        from workbench.experiments import prepare_avo_recovery
        _, complete = prepare_avo_recovery(path.parent, output)
        if complete:
            shutil.rmtree(output, ignore_errors=True)
            raise ValueError("This campaign already has a final result")
        artifact = output / "campaign"
        command = launch_command(mode="campaign", harness=spec["harness"], model=spec["model"],
                                 effort=spec["effort"] or "medium", game_id=spec["game_id"],
                                 backend_url=spec["backend_url"] or default_backend_url(), output=output,
                                 budget=budget, optimizer_model=spec["optimizer_model"],
                                 optimizer_effort=spec["optimizer_effort"],
                                 world_model_mode=spec["world_model_mode"] if spec["world_model_mode"] in {"final-only", "between-hypotheses"} else "final-only",
                                 provider=spec["provider"] or "", resume=True)
    else:
        marker = path / "recovery.json"
        if read_json(marker).get("resumed_as"):
            raise Conflict("This run already has a continuation")
        if read_json(path / "result.json").get("solved") is True:
            raise ValueError("This run already solved its game")
        artifact = output
        command = launch_command(mode=mode, harness=spec["harness"], model=spec["model"],
                                 effort=spec["effort"] or "medium", game_id=spec["game_id"],
                                 backend_url=spec["backend_url"] or default_backend_url(), output=output,
                                 budget=budget, provider=spec["provider"] or "", continue_from=path)
    is_campaign = mode == "campaign" or is_avo
    row = {"id": artifact.relative_to(root).as_posix(), "launcher": "harnesses", "kind": "avo" if is_campaign else "codex",
           "mode": "campaign" if is_campaign else mode, "harness": spec["harness"], "agent_backend": spec["harness"],
           "model": spec["model"], "model_provider": model_provider(spec["model"]),
           "optimizer_model": spec["optimizer_model"], "effort": spec["effort"],
           "optimizer_effort": spec["optimizer_effort"], "game_id": spec["game_id"],
           "world_model_mode": spec["world_model_mode"] if is_campaign else None,
           "condition": None if is_campaign else mode, "provider": spec["provider"] or None, "repeat": 1,
           "pair_id": None, "resumed_from": run_id, "max_wall_seconds": int(budget.get("max_wall_seconds") or 0),
           "output": str(output), "command": command, "status": "queued"}
    return row, marker


def resume_runs(run_ids: list[str], root: Path = ROOT, recovery_of: str | None = None,
                skip_unavailable: bool = False) -> dict:
    """One recovery batch for the given runs. With `skip_unavailable`, runs that
    are complete, solved or already resumed are left out instead of failing."""
    directory = new_job_directory(root, "resume")
    if not directory.resolve().is_relative_to((root / "output/workbench").resolve()):
        raise ValueError("Recovery output is outside Workbench")
    rows, markers, skipped = [], [], []
    try:
        for run_id in run_ids:
            output = directory / f"run-{len(rows) + 1:04d}"
            try:
                row, marker = plan_resume(run_id, output, root)
            except ValueError as exc:
                if not skip_unavailable:
                    raise
                skipped.append(f"{run_id}: {exc}")
                continue
            rows.append(row)
            markers.append(marker)
        if not rows:
            raise ValueError("No run in this selection can be resumed" + (f" ({'; '.join(skipped)})" if skipped else ""))
        directory.mkdir(parents=True, exist_ok=True)
        wall = max(int(r["max_wall_seconds"]) for r in rows)
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "heartbeat": time.time(),
                    "status": "starting", "recovery_of": recovery_of or run_ids[0], "skipped": skipped,
                    "config": {"kind": "matrix", "launcher": "harnesses", "parallel": min(len(rows), 6),
                               "repeats": 1, "comparison": False, "budget": {"max_wall_seconds": wall}},
                    "runs": rows}
        stamp = datetime.now(timezone.utc).isoformat()
        for row, marker in zip(rows, markers):
            write_json(marker, {"resumed_as": row["id"], "created_at": stamp})
        try:
            start_job(directory, manifest, root)
        except OSError:
            for marker in markers:
                marker.unlink(missing_ok=True)
            raise
    except BaseException:
        if directory.is_dir() and not (directory / "job.json").is_file():
            shutil.rmtree(directory, ignore_errors=True)
        raise
    job_id = directory.relative_to(root).as_posix()
    return {"job_id": job_id, "id": job_id, "runs": [r["id"] for r in rows], "run_id": rows[0]["id"],
            "run": rows[0]["id"], "count": len(rows), "skipped": skipped}
