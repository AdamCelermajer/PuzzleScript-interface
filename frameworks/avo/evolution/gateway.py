from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Mapping

from frameworks.avo.core.framework import JsonValue, _jsonable
from frameworks.avo.evolution.evaluator import RunCandidateEvaluator
from frameworks.avo.evolution.store import EvolutionStore
from frameworks.world_model import final_prompt


@dataclass(frozen=True)
class EvolutionBudget:
    max_evaluations: int = 10
    max_wall_seconds: float = 14_400


FINAL_WORLD_MODEL_PROMPT = final_prompt()  # the shared research-note format (frameworks/world_model.py)


class EvolutionGateway:
    """Trusted tools for the outer variation operator; it has no game controls."""

    def __init__(
        self,
        store: EvolutionStore,
        evaluator: RunCandidateEvaluator,
        *,
        mission: str,
        initial_observation: Mapping[str, Any] | None = None,
        budget: EvolutionBudget | None = None,
        world_model_mode: str = "off",
        research_moves_schedule: tuple[int, ...] = (),
    ) -> None:
        self.store = store
        self.evaluator = evaluator
        self.mission = mission
        self.initial_observation: JsonValue = _jsonable(initial_observation)
        self.budget = budget or EvolutionBudget()
        self.started_at = time.monotonic()
        self.finished = False
        self.finish_reason = ""
        self._lock = threading.Lock()
        if world_model_mode not in {"off", "final-only", "between-hypotheses"}:
            raise ValueError("Invalid world-model mode")
        self.world_model_mode = world_model_mode
        # Research moves per attempt, in order; a crashed attempt is not recorded, so it retries the same rung.
        self.research_moves_schedule = tuple(research_moves_schedule)
        self._final_report_requested = False

    def finalization_instruction(self) -> str | None:
        """One last turn in the same outer session, after evaluation is closed."""
        if self.world_model_mode == "off" or self._final_report_requested:
            return None
        self.handle("finish", {"reason": self.finish_reason or "search finished"})
        self._final_report_requested = True
        return FINAL_WORLD_MODEL_PROMPT

    @property
    def success(self) -> bool:
        return any(bool(item["success"]) for item in self.store.evaluations())

    @property
    def terminal(self) -> bool:
        return (
            self.success
            or len(self.store.evaluations()) >= self.budget.max_evaluations
            or (self.budget.max_wall_seconds > 0 and time.monotonic() - self.started_at >= self.budget.max_wall_seconds)
        )

    def next_research_moves(self) -> int | None:
        if not self.research_moves_schedule:
            return None
        used = len(self.store.evaluations())
        return self.research_moves_schedule[min(used, len(self.research_moves_schedule) - 1)]

    def _budgets(self) -> dict[str, float | int]:
        used = len(self.store.evaluations())
        schedule = {"research_moves_schedule": list(self.research_moves_schedule),
                    "next_attempt_research_moves": self.next_research_moves()} if self.research_moves_schedule else {}
        return {
            **schedule,
            "evaluations_used": used,
            "evaluations_remaining": max(0, self.budget.max_evaluations - used),
            "wall_seconds_remaining": None if self.budget.max_wall_seconds == 0 else max(
                0.0,
                self.budget.max_wall_seconds - (time.monotonic() - self.started_at),
            ),
        }

    def _status(self) -> dict[str, Any]:
        if not self.finished and self.success:
            self.finished = True
            self.finish_reason = "a run candidate solved the task"
        if not self.finished and len(self.store.evaluations()) >= self.budget.max_evaluations:
            self.finished = True
            self.finish_reason = "candidate evaluation budget exhausted"
        if not self.finished and self.budget.max_wall_seconds > 0 and time.monotonic() - self.started_at >= self.budget.max_wall_seconds:
            self.finished = True
            self.finish_reason = "outer wall-time budget exhausted"
        population = self.store.population_summary()
        return {
            "finished": self.finished,
            "finish_reason": self.finish_reason,
            "task": {
                "terminal": self.terminal,
                "success": self.success,
                "best": population["best"],
            },
            "budgets": self._budgets(),
        }

    def _require_active(self) -> None:
        status = self._status()
        if status["finished"]:
            raise RuntimeError(f"Evolution already finished: {status['finish_reason']}")

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        params = params or {}
        with self._lock:
            if method == "population":
                return self.store.population_summary()
            if method == "initial":
                return {"observation": self.initial_observation}
            if method == "inspect":
                return self.store.inspect(str(params.get("candidate_id", "")))
            if method == "evidence":
                return self.store.evidence(
                    str(params.get("candidate_id", "")),
                    str(params.get("phase", "")),
                    offset=int(params.get("offset", 0)),
                    limit=int(params.get("limit", 20)),
                )
            if method == "fork":
                self._require_active()
                return self.store.fork(
                    str(params.get("parent_id", "")),
                    str(params.get("child_id", "")),
                )
            if method == "register":
                self._require_active()
                return self.store.register_draft(
                    str(params.get("candidate_id", ""))
                ).record()
            if method == "evaluate":
                self._require_active()
                candidate_id = str(params.get("candidate_id", ""))
                if self.store.evaluations(candidate_id):
                    raise ValueError(
                        f"{candidate_id} is already evaluated; fork a child to vary it"
                    )
                candidate = self.store.get_candidate(candidate_id)
                moves = self.next_research_moves()
                evaluation = self.evaluator.evaluate(
                    candidate,
                    self.store.next_run_dir(candidate.candidate_id),
                    **({"research_moves": moves} if moves is not None else {}),
                )
                evaluation = replace(evaluation, score={**evaluation.score,
                    "search_session_elapsed_seconds": time.monotonic() - self.started_at})
                self.store.record_evaluation(evaluation)
                status = self._status()
                return {"evaluation": evaluation.record(), "status": status}
            if method == "status":
                return self._status()
            if method == "finish":
                self.finished = True
                self.finish_reason = str(params.get("reason", "optimizer requested stop"))
                return self._status()
            raise ValueError(f"Unknown evolution tool: {method}")
