from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from workbench.models import (
    CODEX_PROVIDER_ID,
    DEFAULT_CODEX_MODEL,
    DEFAULT_MODEL,
    PROVIDER_ID,
    public_model_catalog,
    validate_codex_model_selection,
    validate_model_selection,
)
from workbench import openrouter_account
from workbench.run_manager import RunManager
from experiement.bfs_solver.web_api import create_optimal_path_router
from experiement.bfs_solver.web_manager import OptimalPathManager


class StartRunRequest(BaseModel):
    agent_mode: Literal["rule", "codex"] = "rule"
    provider: Literal["openrouter", "codex_oauth"] = PROVIDER_ID
    model: str = DEFAULT_MODEL
    reasoning_effort: str = ""
    backend: Literal["puzzlescript", "arc"] = "puzzlescript"
    game_id: str = Field(default="ps_sokoban_basic-v1", min_length=1, max_length=160)
    max_steps: int = Field(default=12, ge=1, le=200)
    memory_mode: Literal["fresh", "resume"] = "fresh"
    provide_legend: bool = True
    provide_end_goal: bool = True
    end_goal: str = Field(default="complete the level", max_length=500)

    @field_validator("game_id")
    @classmethod
    def game_id_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("game_id must not be blank")
        return stripped

    @field_validator("end_goal")
    @classmethod
    def end_goal_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("end_goal must not be blank")
        return stripped

    @model_validator(mode="after")
    def model_and_effort_must_match(self) -> "StartRunRequest":
        if self.agent_mode == "codex":
            self.provider = CODEX_PROVIDER_ID
            if self.model == DEFAULT_MODEL:
                self.model = DEFAULT_CODEX_MODEL
            if not self.reasoning_effort:
                self.reasoning_effort = "low"
            validate_codex_model_selection(self.model, self.reasoning_effort)
        else:
            self.provider = PROVIDER_ID
            validate_model_selection(self.model, self.reasoning_effort)
        return self


class ReplaceOpenRouterKeyRequest(BaseModel):
    api_key: str = Field(min_length=10, max_length=512)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("api_key must not be blank")
        return stripped


class PromptUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)


def create_app(
    manager: RunManager | None = None,
    optimal_path_manager: OptimalPathManager | None = None,
) -> FastAPI:
    run_manager = manager or RunManager()
    path_manager = optimal_path_manager or OptimalPathManager()
    app = FastAPI(
        title="PuzzleScript Workbench",
        version="1.0.0",
    )
    app.state.run_manager = run_manager
    app.state.optimal_path_manager = path_manager
    app.include_router(create_optimal_path_router(path_manager))

    @app.get("/api/workbench/health")
    def health() -> dict:
        return run_manager.health()

    @app.get("/api/workbench/games")
    def games(backend: Literal["puzzlescript", "arc"] = Query("puzzlescript")) -> dict:
        if backend == "arc":
            return {"backend": backend, "games": []}
        try:
            catalog = run_manager.local_games()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Local PuzzleScript catalog unavailable: {exc}",
            ) from exc
        return {"backend": backend, "games": catalog}

    @app.get("/api/workbench/models")
    def models() -> dict:
        return public_model_catalog()

    @app.get("/api/workbench/codex/status")
    def codex_status(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return run_manager.codex_status()

    @app.get("/api/workbench/prompts")
    def prompts(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return {"prompts": run_manager.prompt_store.catalog()}

    @app.put("/api/workbench/prompts/{prompt_id}")
    def save_prompt(
        prompt_id: str, request: PromptUpdateRequest, response: Response
    ) -> dict:
        response.headers["Cache-Control"] = "no-store"
        if run_manager.has_active_run():
            raise HTTPException(
                status_code=409,
                detail="Stop the active run before changing prompts",
            )
        try:
            return {"saved": True, "prompt": run_manager.prompt_store.save(
                prompt_id, request.content
            )}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/workbench/prompts/{prompt_id}")
    def reset_prompt(prompt_id: str, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        if run_manager.has_active_run():
            raise HTTPException(
                status_code=409,
                detail="Stop the active run before changing prompts",
            )
        try:
            return {
                "reset": True,
                "prompt": run_manager.prompt_store.reset(prompt_id),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/workbench/openrouter/status")
    def openrouter_status(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return openrouter_account.get_status()

    @app.post("/api/workbench/openrouter/key")
    def replace_openrouter_key(
        request: ReplaceOpenRouterKeyRequest,
        response: Response,
    ) -> dict:
        response.headers["Cache-Control"] = "no-store"
        if run_manager.has_active_run():
            raise HTTPException(
                status_code=409,
                detail="Stop the active run before replacing the OpenRouter key",
            )
        try:
            status = openrouter_account.replace_key(request.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"saved": True, "status": status}

    @app.post("/api/workbench/runs", status_code=202)
    def start_run(request: StartRunRequest) -> dict:
        payload = request.model_dump()
        try:
            run = run_manager.start(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return run.snapshot()

    @app.get("/api/workbench/runs/current")
    def current_run(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        run = run_manager.current()
        return {"run": run.snapshot() if run is not None else None}

    @app.get("/api/workbench/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        try:
            return run_manager.get(run_id).snapshot()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/workbench/runs/{run_id}/stop", status_code=202)
    def stop_run(run_id: str) -> dict:
        try:
            return run_manager.stop(run_id).snapshot()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/workbench/artifacts")
    def artifacts(game_id: str = Query(..., min_length=1, max_length=160)) -> dict:
        return {"game_id": game_id, "artifacts": run_manager.list_artifacts(game_id)}

    @app.get("/api/workbench/artifacts/{artifact_id}")
    def artifact_replay(
        artifact_id: str,
        game_id: str = Query(..., min_length=1, max_length=160),
    ) -> dict:
        try:
            return run_manager.artifact_replay(game_id, artifact_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/workbench/artifacts/{artifact_id}", status_code=204)
    def delete_artifact(
        artifact_id: str,
        game_id: str = Query(..., min_length=1, max_length=160),
    ) -> Response:
        try:
            run_manager.delete_artifact(game_id, artifact_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    return app


app = create_app()
