from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import requests
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from benchmark.agents import RandomAgent, SimulatedPartialAgent
from benchmark.service import BenchmarkRunManager


WEB_ROOT = Path(__file__).with_name("web")


class RepresentationRequest(BaseModel):
    rendered_image: bool = False
    legend: bool = False
    action_semantics: bool = False


class CreateRunRequest(BaseModel):
    capabilities: list[Literal["rule_learning", "closeness"]] = Field(
        default_factory=lambda: ["rule_learning", "closeness"]
    )
    sample_size: int | None = Field(default=5, ge=1)
    seed: int = 0
    selected_games: list[str] | None = None
    representation: RepresentationRequest = Field(
        default_factory=RepresentationRequest
    )


class ResetRequest(BaseModel):
    game_id: str
    card_id: str
    guid: str | None = None


class ActionRequest(BaseModel):
    game_id: str
    guid: str
    reasoning: Any | None = None
    x: int | None = None
    y: int | None = None


class CloseScorecardRequest(BaseModel):
    card_id: str


class RulePredictionRequest(BaseModel):
    probe_id: str
    predicted_frame: list[list[int]]


class SubmitRuleChallengeRequest(BaseModel):
    predictions: list[RulePredictionRequest]


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(
            status_code=404, detail=f"Not found: {exc.args[0]}"
        )
    if isinstance(exc, (ValueError, RuntimeError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, requests.RequestException):
        return HTTPException(
            status_code=502,
            detail=f"Upstream ARC service failed: {exc}",
        )
    return HTTPException(status_code=500, detail=str(exc))


def create_app(manager: BenchmarkRunManager | None = None) -> FastAPI:
    run_manager = manager or BenchmarkRunManager()
    app = FastAPI(
        title="PuzzleScript Learning Benchmark",
        description=(
            "Periodic rule-learning challenges and per-level closeness scores."
        ),
        version="0.4.0",
    )
    app.state.run_manager = run_manager

    if WEB_ROOT.exists():
        app.mount(
            "/benchmark-static",
            StaticFiles(directory=WEB_ROOT),
            name="benchmark-static",
        )

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_ROOT / "index.html")

    @app.get("/api/benchmark/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "catalog_id": run_manager.catalog["catalog_id"],
            "catalog_version": run_manager.catalog["version"],
            "games": len(run_manager.catalog["games"]),
            "capabilities": ["rule_learning", "closeness"],
        }

    @app.get("/api/benchmark/catalog")
    def catalog() -> dict[str, Any]:
        artifacts = run_manager.artifact_summary()
        return {
            "catalog_id": run_manager.catalog["catalog_id"],
            "version": run_manager.catalog["version"],
            "source": run_manager.catalog["source"],
            "game_count": len(run_manager.catalog["games"]),
            "capabilities": {
                capability: sum(
                    bool(
                        game.get("tracks", {})
                        .get(capability, {})
                        .get("enabled")
                    )
                    for game in run_manager.catalog["games"]
                )
                for capability in ("rule_learning", "closeness")
            },
            "artifact_summary": artifacts["summary"],
        }

    @app.get("/api/benchmark/artifacts")
    def artifacts() -> dict[str, Any]:
        return run_manager.artifact_summary()

    @app.get("/api/benchmark/contract")
    def contract() -> dict[str, Any]:
        return {
            "version": "0.4.0",
            "run_model": "one_game_stream_two_learning_scores",
            "create_run": {
                "method": "POST",
                "path": "/api/benchmark/runs",
                "selects": [
                    "capabilities",
                    "sample_size",
                    "seed",
                    "representation",
                ],
                "returns": [
                    "run_id",
                    "run_token",
                    "monitor_token",
                    "game_ids",
                    "action_budgets",
                ],
            },
            "agent_auth": {
                "header": "X-API-Key",
                "value": "run_token",
                "visibility": "opaque game identities",
            },
            "monitor_auth": {
                "header": "X-Monitor-Key",
                "value": "monitor_token",
                "visibility": (
                    "evaluator identities, frames, artifact coverage, "
                    "challenges, and scores"
                ),
            },
            "interaction": {
                "games": "GET /api/games",
                "scorecard": "POST /api/scorecard/open",
                "reset": "POST /api/cmd/RESET",
                "actions": "POST /api/cmd/ACTION1..5 or ACTION7",
                "challenge_delivery": (
                    "RESET and periodic action responses may include "
                    "benchmark_challenge"
                ),
                "challenge_checkpoints": [
                    "level_start",
                    "every_10_actions",
                    "level_complete",
                    "budget_end",
                ],
                "challenge_submission": (
                    "POST /api/benchmark/runs/{run_id}/rule-challenges/"
                    "{challenge_id}"
                ),
                "close": "POST /api/benchmark/runs/{run_id}/close",
            },
            "scores": {
                "rule_learning": {
                    "agent_output": (
                        "predicted f2 frame for each hidden <f1, action, f2> "
                        "probe"
                    ),
                    "ground_truth": (
                        "saved replay-verified PuzzleScript transitions"
                    ),
                    "primary_metric": (
                        "latest_macro_exact_frame_accuracy"
                    ),
                    "also_reports": [
                        "cell_accuracy",
                        "transition_edit_f1",
                        "coverage",
                        "learning_curve",
                    ],
                },
                "closeness": {
                    "agent_output": "environment actions",
                    "ground_truth": (
                        "distance along a saved replay-verified level solution"
                    ),
                    "primary_metric": "mean_level_closeness",
                    "completed_level": "100%",
                    "off_saved_trace": "unavailable, never treated as zero",
                },
            },
        }

    @app.post("/api/benchmark/runs", status_code=201)
    def create_run(request: CreateRunRequest) -> dict[str, Any]:
        try:
            run = run_manager.create(
                capabilities=request.capabilities,
                sample_size=request.sample_size,
                seed=request.seed,
                selected_games=request.selected_games,
                representation=request.representation.model_dump(),
            )
            return {
                **run.public(),
                "run_token": run.token,
                "monitor_token": run.monitor_token,
            }
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/benchmark/simulated-partial-agent", status_code=201)
    def run_simulated_partial_agent() -> dict[str, Any]:
        try:
            return SimulatedPartialAgent().run(run_manager)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post(
        "/api/benchmark/simulated-partial-agent/live",
        status_code=201,
    )
    def start_simulated_partial_agent(
        delay_seconds: float = Query(default=0.5, ge=0, le=5),
    ) -> dict[str, Any]:
        try:
            return SimulatedPartialAgent().start(
                run_manager,
                delay_seconds=delay_seconds,
            )
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/benchmark/random-agent/live", status_code=201)
    def start_random_agent(
        delay_seconds: float = Query(default=0.5, ge=0, le=5),
    ) -> dict[str, Any]:
        try:
            return RandomAgent().start(
                run_manager,
                delay_seconds=delay_seconds,
            )
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/api/benchmark/runs/{run_id}")
    def get_run(
        run_id: str,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, Any]:
        try:
            return run_manager.require(run_id, x_api_key).public()
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/api/benchmark/runs/{run_id}/monitor")
    def monitor_run(
        run_id: str,
        x_monitor_key: str = Header(default="", alias="X-Monitor-Key"),
    ) -> dict[str, Any]:
        try:
            return run_manager.monitor(run_id, x_monitor_key)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post(
        "/api/benchmark/runs/{run_id}/rule-challenges/{challenge_id}"
    )
    def submit_rule_challenge(
        run_id: str,
        challenge_id: str,
        request: SubmitRuleChallengeRequest,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, Any]:
        try:
            return run_manager.submit_rule_predictions(
                run_id,
                x_api_key,
                challenge_id,
                [
                    prediction.model_dump()
                    for prediction in request.predictions
                ],
            )
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/benchmark/runs/{run_id}/close")
    def close_run(
        run_id: str,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, Any]:
        try:
            return run_manager.close(run_id, x_api_key)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/api/games")
    def games(
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> list[dict[str, str]]:
        try:
            run = run_manager.from_token(x_api_key)
            return [
                {"game_id": alias, "title": "Hidden benchmark environment"}
                for alias in run.public()["game_ids"]
            ]
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/api/games/{game_alias}")
    def game_info(
        game_alias: str,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, str]:
        try:
            run = run_manager.from_token(x_api_key)
            if game_alias not in run.reverse_aliases:
                raise KeyError(game_alias)
            return {
                "game_id": game_alias,
                "title": "Hidden benchmark environment",
            }
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/scorecard/open")
    def open_scorecard(
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, str]:
        try:
            run = run_manager.from_token(x_api_key)
            return {"card_id": run.run_id}
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.get("/api/scorecard/{card_id}")
    def get_scorecard(
        card_id: str,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, Any]:
        try:
            return run_manager.scorecard(card_id, x_api_key)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/scorecard/close")
    def close_scorecard(
        request: CloseScorecardRequest,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, Any]:
        try:
            return run_manager.close(request.card_id, x_api_key)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/cmd/RESET")
    def reset(
        request: ResetRequest,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, Any]:
        try:
            return run_manager.reset(
                request.card_id,
                x_api_key,
                game_alias=request.game_id,
                guid=request.guid,
            )
        except Exception as exc:
            raise _translate_error(exc) from exc

    @app.post("/api/cmd/{action_name}")
    def action(
        action_name: str,
        request: ActionRequest,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> dict[str, Any]:
        action_id = action_name.upper()
        if action_id not in {
            "ACTION1",
            "ACTION2",
            "ACTION3",
            "ACTION4",
            "ACTION5",
            "ACTION7",
        }:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported ARC action: {action_name}",
            )
        try:
            data = (
                {"x": request.x, "y": request.y}
                if request.x is not None and request.y is not None
                else None
            )
            return run_manager.action(
                x_api_key,
                action=action_id,
                game_alias=request.game_id,
                guid=request.guid,
                data=data,
            )
        except Exception as exc:
            raise _translate_error(exc) from exc

    return app


app = create_app()
