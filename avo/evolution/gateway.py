from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from avo.evolution.evaluator import RunCandidateEvaluator
from avo.evolution.store import EvolutionStore


@dataclass(frozen=True)
class EvolutionBudget:
    max_evaluations: int = 6
    max_wall_seconds: float = 14_400


class EvolutionGateway:
    """Trusted tools for the outer variation operator; it has no game controls."""

    def __init__(
        self,
        store: EvolutionStore,
        evaluator: RunCandidateEvaluator,
        *,
        mission: str,
        budget: EvolutionBudget | None = None,
    ) -> None:
        self.store = store
        self.evaluator = evaluator
        self.mission = mission
        self.budget = budget or EvolutionBudget()
        self.started_at = time.monotonic()
        self.finished = False
        self.finish_reason = ""
        self._lock = threading.Lock()

    @property
    def success(self) -> bool:
        return any(bool(item["success"]) for item in self.store.evaluations())

    @property
    def terminal(self) -> bool:
        return (
            self.success
            or len(self.store.evaluations()) >= self.budget.max_evaluations
            or time.monotonic() - self.started_at >= self.budget.max_wall_seconds
        )

    def _budgets(self) -> dict[str, float | int]:
        used = len(self.store.evaluations())
        return {
            "evaluations_used": used,
            "evaluations_remaining": max(0, self.budget.max_evaluations - used),
            "wall_seconds_remaining": max(
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
        if not self.finished and time.monotonic() - self.started_at >= self.budget.max_wall_seconds:
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
            if method == "inspect":
                return self.store.inspect(str(params.get("candidate_id", "")))
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
                evaluation = self.evaluator.evaluate(
                    candidate,
                    self.store.next_run_dir(candidate.candidate_id),
                )
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
