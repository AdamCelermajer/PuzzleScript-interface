"""Workbench launch plans and artifact APIs for maintained experiment runners."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from workbench.catalog import ROOT, last_record, read_json, run_path, snapshot


class ExperimentRequest(BaseModel):
    kind: Literal["avo", "codex"]
    agent_backend: Literal["codex"] = "codex"
    comparison: bool = False
    game_ids: list[str] = Field(min_length=1, max_length=30)
    models: list[str] = Field(default_factory=lambda: ["gpt-5.6-sol"], min_length=1, max_length=8)
    efforts: list[Literal["minimal", "low", "medium", "high", "xhigh"]] = Field(default_factory=lambda: ["low"], min_length=1, max_length=5)
    conditions: list[Literal["baseline", "baseline-plus"]] = Field(default_factory=lambda: ["baseline-plus"], min_length=1, max_length=2)
    world_model_modes: list[Literal["final-only", "between-hypotheses"]] = Field(default_factory=lambda: ["final-only"], min_length=1, max_length=2)
    optimizer_model: str = "gpt-6-astra"
    optimizer_effort: Literal["low", "medium", "high", "xhigh"] = "low"
    service_tier: Literal["", "priority"] = ""
    backend_url: str = "http://localhost:8000"
    repeats: int = Field(default=1, ge=1, le=20)
    parallel: int = Field(default=1, ge=1, le=6)
    max_steps: int = Field(default=100, ge=1, le=10000)
    max_evaluations: int = Field(default=10, ge=1, le=100)
    research_moves: int = Field(default=300, ge=1, le=10000)
    solver_moves: int = Field(default=1500, ge=1, le=20000)
    max_hours: float = Field(default=4, gt=0, le=24)
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
        if self.comparison:
            if self.kind != "avo":
                raise ValueError("Matched world-model comparisons are available for AVO only")
            self.world_model_modes = ["final-only", "between-hypotheses"]
            if self.parallel not in {2, 4, 6}:
                raise ValueError("Comparisons need 2, 4 or 6 parallel slots so each pair starts together")
        from avo.client.model_provider import resolve_model
        for model in [*self.models, self.optimizer_model]:
            provider, _ = resolve_model(model)
            if provider == "openrouter" and self.kind != "avo":
                raise ValueError("OpenRouter through Codex is currently available for AVO only")
        if self.service_tier and any(resolve_model(m)[0] == "openrouter" for m in self.models):
            raise ValueError("OpenRouter players do not support the Codex service tier setting")
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


def plan_runs(config: ExperimentRequest, directory: Path, root: Path = ROOT) -> list[dict]:
    from itertools import product
    parent = None
    if config.continue_from:
        parent = run_path(config.continue_from, root)
        from studies.codex_agent.continuation import load_parent
        load_parent(parent)
        saved = read_json(parent / "run_config.json")
        expected = {"game_id": config.game_ids[0], "model": config.models[0], "reasoning_effort": config.efforts[0], "condition": config.conditions[0]}
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
                        "--player-service-tier", config.service_tier, "--max-evaluations", str(config.max_evaluations),
                        "--world-model-mode", condition,
                        "--research-moves", str(config.research_moves), "--solver-moves", str(config.solver_moves),
                        "--max-wall-seconds", str(int(config.max_hours * 3600)), "--output-dir", str(output)]
            artifact = output / "campaign"
        else:
            command += ["studies.codex_agent.run", "--no-window", "--game-id", game,
                        "--backend-url", config.backend_url, "--model", model, "--effort", effort,
                        "--condition", condition, "--max-steps", str(config.max_steps), "--output-dir", str(output)]
            if parent:
                command += ["--continue-from", str(parent)]
            artifact = output
        rows.append({"id": artifact.relative_to(root).as_posix(), "kind": config.kind, "game_id": game,
                     "agent_backend": config.agent_backend,
                     "pair_id": pairs[pair_key] if config.comparison else None,
                     "model_provider": "openrouter" if model.startswith("openrouter/") else "openai",
                     "optimizer_model": config.optimizer_model if config.kind == "avo" else None,
                     "model": model, "effort": effort, "condition": condition if config.kind == "codex" else None,
                     "world_model_mode": condition if config.kind == "avo" else None, "repeat": repeat + 1,
                     "output": str(output), "command": command, "status": "queued"})
    return rows


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(.1)


def create_router(root: Path = ROOT) -> APIRouter:
    router = APIRouter(prefix="/api/workbench")
    cache: dict = {}

    @router.get("/model-catalog")
    def models(provider: Literal["openrouter"] = "openrouter"):
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

    @router.get("/catalog")
    def catalog(response: Response):
        response.headers["Cache-Control"] = "no-store"
        if time.monotonic() - cache.get("at", 0) > 3:
            cache.update(data=snapshot(root), at=time.monotonic())
        # Do not expose saved process commands through the public listing.
        data = cache["data"]
        return {**data, "jobs": [{**job, "runs": [{k: v for k, v in row.items() if k not in {"command", "output"}} for row in job["runs"]]} for job in data["jobs"]]}

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
        names = ["run_config.json", "result.json", "error.json", "restoration.json", "transitions.jsonl", "transcript.jsonl", "codex_session.jsonl", "isolation_manifest.json"]
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
            allowed = {"run_config.json", "result.json", "error.json", "restoration.json", "transitions.jsonl", "transcript.jsonl", "codex_session.jsonl", "isolation_manifest.json"}
            note = len(Path(file).parts) == 2 and Path(file).parts[0] == "workspace" and target.suffix == ".md"
            if not target.is_relative_to(path) or not (file in allowed or note):
                raise ValueError("Invalid artifact")
            if any(p.startswith(".") for p in Path(file).parts) or "model_requests" in Path(file).parts:
                raise ValueError("Artifact is not available here")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not target.is_file():
            raise HTTPException(404, "Artifact not found")
        return FileResponse(target, filename=target.name)

    return router
