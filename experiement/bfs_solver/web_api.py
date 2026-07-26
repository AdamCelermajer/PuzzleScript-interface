from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from experiement.bfs_solver.web_manager import OptimalPathManager


class StartOptimalPathRequest(BaseModel):
    game_id: str = Field(min_length=1, max_length=160)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    max_states: int = Field(default=100_000, ge=1_000, le=1_000_000)

    @field_validator("game_id")
    @classmethod
    def game_id_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("game_id must not be blank")
        return stripped


def create_optimal_path_router(manager: OptimalPathManager) -> APIRouter:
    router = APIRouter(prefix="/api/optimal-path", tags=["optimal-path"])

    @router.get("/games")
    def games() -> dict:
        return {"games": manager.games()}

    @router.post("/runs", status_code=202)
    def start_run(request: StartOptimalPathRequest) -> dict:
        try:
            return manager.start(request.model_dump()).snapshot()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/runs/current")
    def current_run(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        run = manager.current()
        return {"run": run.snapshot() if run is not None else None}

    @router.get("/runs/{run_id}")
    def get_run(run_id: str, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        try:
            return manager.get(run_id).snapshot()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/runs/{run_id}/stop", status_code=202)
    def stop_run(run_id: str) -> dict:
        try:
            return manager.stop(run_id).snapshot()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
