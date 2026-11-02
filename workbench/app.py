from __future__ import annotations

import os
from typing import Literal

import requests
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from harnesses.codex import codex_oauth_status
from workbench.paper_investigation import CodexPaperAssistant, PaperAssistant
from workbench.paper_library import PaperLibrary
from workbench.experiments import create_router as create_experiments_router
from experiement.bfs_solver.web_api import create_optimal_path_router
from experiement.bfs_solver.web_manager import OptimalPathManager


class PaperChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)


class PaperQuestionRequest(BaseModel):
    paper: str | None = Field(default=None, min_length=1, max_length=96)
    paper_ids: list[str] = Field(default_factory=list, max_length=8)
    annotation_ids: list[str] = Field(default_factory=list, max_length=50)
    question: str = Field(min_length=1, max_length=6_000)
    selected_passage: str = Field(default="", max_length=5_000)
    history: list[PaperChatTurn] = Field(default_factory=list, max_length=10)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank")
        return stripped

    @field_validator("selected_passage")
    @classmethod
    def strip_selected_passage(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def paper_selection_must_not_be_empty(self) -> "PaperQuestionRequest":
        selected = self.paper_ids or ([self.paper] if self.paper else [])
        if not selected:
            raise ValueError("Choose at least one paper")
        self.paper_ids = list(dict.fromkeys(selected))
        return self


class PaperImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2_000)
    title: str = Field(default="", max_length=500)
    authors: str = Field(default="", max_length=1_000)


class PaperUpdateRequest(BaseModel):
    status: Literal["unread", "reading", "finished"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    authors: str | None = Field(default=None, max_length=1_000)
    last_page: int | None = Field(default=None, ge=0, le=100_000)


class PaperAnnotationCreate(BaseModel):
    id: str | None = Field(default=None, max_length=96)
    quote: str = Field(min_length=1, max_length=5_000)
    page: int | None = Field(default=None, ge=1, le=100_000)
    section: str = Field(default="", max_length=500)
    view: str = Field(default="source", max_length=40)
    anchor: dict | None = None
    comment: str = Field(default="", max_length=10_000)
    created_at: str | None = Field(default=None, max_length=80)


class PaperAnnotationUpdate(BaseModel):
    comment: str = Field(default="", max_length=10_000)


class PaperQuestionRecordCreate(BaseModel):
    id: str | None = Field(default=None, max_length=96)
    question: str = Field(min_length=1, max_length=6_000)
    answer: str = Field(min_length=1, max_length=20_000)
    annotation_ids: list[str] = Field(default_factory=list, max_length=50)
    selected_passage: str = Field(default="", max_length=5_000)
    created_at: str | None = Field(default=None, max_length=80)


def create_app(
    optimal_path_manager: OptimalPathManager | None = None,
    paper_assistant: PaperAssistant | None = None,
    paper_library: PaperLibrary | None = None,
) -> FastAPI:
    path_manager = optimal_path_manager or OptimalPathManager()
    research_assistant = paper_assistant or CodexPaperAssistant()
    library = paper_library or PaperLibrary()
    app = FastAPI(
        title="PuzzleScript Workbench",
        version="1.0.0",
    )
    # Run catalogs and submissions are large JSON; compress them for remote (Tailscale) viewers.
    app.add_middleware(GZipMiddleware, minimum_size=4096)
    app.state.optimal_path_manager = path_manager
    app.state.paper_assistant = research_assistant
    app.state.paper_library = library
    from workbench.benchmarks import router as benchmarks_router
    from workbench.diary import router as diary_router
    from workbench.results import router as results_router
    from workbench.board import router as board_router

    app.include_router(create_optimal_path_router(path_manager))
    app.include_router(create_experiments_router())
    app.include_router(benchmarks_router)
    app.include_router(diary_router)
    app.include_router(results_router)
    app.include_router(board_router)

    @app.get("/api/workbench/health")
    def health() -> dict:
        return {"ok": True, "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
                "arc_configured": bool(os.getenv("ARC_API_KEY"))}

    @app.get("/api/workbench/games")
    def games(backend: Literal["puzzlescript", "arc"] = Query("puzzlescript")) -> dict:
        if backend == "arc":
            return {"backend": backend, "games": []}
        try:
            response = requests.get("http://127.0.0.1:8000/api/games", timeout=10)
            response.raise_for_status()
            catalog = response.json() if isinstance(response.json(), list) else []
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Local PuzzleScript catalog unavailable: {exc}",
            ) from exc
        return {"backend": backend, "games": catalog}

    @app.get("/api/workbench/codex/status")
    def codex_status(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return codex_oauth_status()

    @app.get("/api/workbench/paper-investigation/papers")
    def list_papers(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return {"papers": library.list_papers(), "library_root": str(library.root)}

    @app.post("/api/workbench/paper-investigation/papers/import", status_code=201)
    def import_paper(request: PaperImportRequest) -> dict:
        try:
            return {"paper": library.import_url(
                request.url, title=request.title, authors=request.authors
            )}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not import PDF: {exc}") from exc

    @app.post("/api/workbench/paper-investigation/papers/upload", status_code=201)
    async def upload_paper(
        request: Request,
        filename: str = Query("paper.pdf", min_length=1, max_length=255),
        title: str = Query("", max_length=500),
        authors: str = Query("", max_length=1_000),
    ) -> dict:
        try:
            return {"paper": library.upload_pdf(
                await request.body(), filename=filename, title=title, authors=authors
            )}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/workbench/paper-investigation/papers/{paper_id}")
    def get_paper(paper_id: str, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        try:
            return {
                "paper": library.get_paper(paper_id),
                "annotations": library.annotations(paper_id),
                "questions": library.questions(paper_id),
            }
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/workbench/paper-investigation/papers/{paper_id}/pdf")
    def paper_pdf(paper_id: str) -> FileResponse:
        try:
            path = library.pdf_path(paper_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type="application/pdf")

    @app.patch("/api/workbench/paper-investigation/papers/{paper_id}")
    def update_paper(paper_id: str, request: PaperUpdateRequest) -> dict:
        try:
            return {"paper": library.update_paper(
                paper_id, request.model_dump(exclude_none=True)
            )}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/workbench/paper-investigation/papers/{paper_id}/annotations",
        status_code=201,
    )
    def add_annotation(paper_id: str, request: PaperAnnotationCreate) -> dict:
        try:
            return {"annotation": library.add_annotation(
                paper_id, request.model_dump(exclude_none=True)
            )}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch(
        "/api/workbench/paper-investigation/papers/{paper_id}/annotations/{annotation_id}"
    )
    def update_annotation(
        paper_id: str, annotation_id: str, request: PaperAnnotationUpdate
    ) -> dict:
        try:
            return {"annotation": library.update_annotation(
                paper_id, annotation_id, request.model_dump()
            )}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete(
        "/api/workbench/paper-investigation/papers/{paper_id}/annotations/{annotation_id}",
        status_code=204,
    )
    def delete_annotation(paper_id: str, annotation_id: str) -> Response:
        try:
            library.delete_annotation(paper_id, annotation_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post(
        "/api/workbench/paper-investigation/papers/{paper_id}/questions",
        status_code=201,
    )
    def import_question(paper_id: str, request: PaperQuestionRecordCreate) -> dict:
        try:
            question = library.save_question(
                [paper_id], request.model_dump(exclude_none=True)
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"question": question}

    @app.post("/api/workbench/paper-investigation/ask")
    def ask_paper_question(request: PaperQuestionRequest, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        try:
            source_context = library.context(
                request.paper_ids, request.annotation_ids
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            answer = research_assistant.ask(
                paper=", ".join(request.paper_ids),
                question=request.question,
                selected_passage=request.selected_passage,
                history=[turn.model_dump() for turn in request.history],
                source_context=source_context,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Research copilot failed: {exc}",
            ) from exc
        saved = library.save_question(
            request.paper_ids,
            {
                "question": request.question,
                "answer": answer,
                "annotation_ids": request.annotation_ids,
                "selected_passage": request.selected_passage,
            },
        )
        return {
            "paper": request.paper_ids[0] if len(request.paper_ids) == 1 else None,
            "paper_ids": request.paper_ids,
            "answer": answer,
            "question_id": saved["id"],
        }

    return app


app = create_app()
