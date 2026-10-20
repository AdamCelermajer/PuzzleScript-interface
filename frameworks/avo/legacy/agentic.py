from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from frameworks.avo.core.framework import (
    Action,
    AvoLaboratory,
    CycleResult,
    Observation,
    SupervisorEvent,
    Transition,
)
from frameworks.avo.core.theory_package import TheoryPackageRegistry


@dataclass(frozen=True)
class SearchBudget:
    max_decisions: int = 100
    max_environment_steps: int = 100
    max_candidates: int = 50
    max_wall_seconds: float = 3600


@dataclass(frozen=True)
class CandidateSummary:
    candidate_id: str
    parent_id: str | None
    claim: str
    complexity: float


@dataclass(frozen=True)
class AgentContext:
    observation: Observation
    history: tuple[Transition, ...]
    candidates: tuple[CandidateSummary, ...]
    available_actions: tuple[str, ...]
    recent_supervisor_events: tuple[SupervisorEvent, ...]
    decisions_remaining: int
    environment_steps_remaining: int
    candidate_slots_remaining: int
    workspace: Path


@dataclass(frozen=True)
class AgentDecision:
    """The framework asks what to do; the agent owns the answer."""

    action: Action | None = None
    rationale: str = ""
    stop_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.action is None) == (self.stop_reason is None):
            raise ValueError("Decision must contain exactly one of action or stop_reason")


class AutonomousResearchAgent(Protocol):
    def decide(self, context: AgentContext) -> AgentDecision:
        """May use tools and create Theory Packages in context.workspace before returning."""


@dataclass(frozen=True)
class AgenticRunResult:
    final_observation: Observation
    cycles: tuple[CycleResult, ...]
    decisions: int
    candidates_created: int
    stop_reason: str


class AgenticVariationRunner:
    """A thin trusted kernel around an autonomous variation operator."""

    def __init__(
        self,
        laboratory: AvoLaboratory,
        agent: AutonomousResearchAgent,
        candidate_workspace: str | Path,
        budget: SearchBudget | None = None,
        terminal_statuses: Sequence[str] = ("WIN", "GAME_OVER"),
    ) -> None:
        self.laboratory = laboratory
        self.agent = agent
        self.registry = TheoryPackageRegistry(candidate_workspace)
        self.budget = budget or SearchBudget()
        self.terminal_statuses = frozenset(terminal_statuses)

    def _discover(self) -> None:
        for candidate in self.registry.discover():
            if candidate.candidate_id not in self.laboratory._candidate_ids:
                if len(self.laboratory.candidates) >= self.budget.max_candidates:
                    raise RuntimeError("Candidate budget exhausted")
                self.laboratory.register_candidate(candidate)

    def run(self) -> AgenticRunResult:
        started = time.monotonic()
        current = self.laboratory.reset()
        cycles: list[CycleResult] = []
        supervisor_events: tuple[SupervisorEvent, ...] = ()
        decisions = 0
        stop_reason = "budget_exhausted"

        while decisions < self.budget.max_decisions and len(cycles) < self.budget.max_environment_steps:
            if time.monotonic() - started >= self.budget.max_wall_seconds:
                stop_reason = "wall_time_exhausted"
                break
            if current.status in self.terminal_statuses:
                stop_reason = f"environment_terminal:{current.status}"
                break

            self._discover()
            context = AgentContext(
                observation=current,
                history=tuple(self.laboratory.history),
                candidates=tuple(
                    CandidateSummary(
                        candidate_id=item.candidate_id,
                        parent_id=item.parent_id,
                        claim=item.claim,
                        complexity=item.complexity,
                    )
                    for item in self.laboratory.candidates
                ),
                available_actions=current.available_actions,
                recent_supervisor_events=supervisor_events,
                decisions_remaining=self.budget.max_decisions - decisions,
                environment_steps_remaining=self.budget.max_environment_steps - len(cycles),
                candidate_slots_remaining=self.budget.max_candidates - len(self.laboratory.candidates),
                workspace=self.registry.root,
            )
            decision = self.agent.decide(context)
            decisions += 1
            self._discover()

            if decision.stop_reason is not None:
                stop_reason = f"agent_stopped:{decision.stop_reason}"
                break
            assert decision.action is not None
            self.laboratory.store.append(
                "agent_decision",
                {"action": decision.action, "rationale": decision.rationale},
            )
            cycle = self.laboratory.step(decision.action)
            cycles.append(cycle)
            current = cycle.transition.after
            supervisor_events = cycle.supervisor_events

        if current.status in self.terminal_statuses:
            stop_reason = f"environment_terminal:{current.status}"

        return AgenticRunResult(
            final_observation=current,
            cycles=tuple(cycles),
            decisions=decisions,
            candidates_created=len(self.laboratory.candidates),
            stop_reason=stop_reason,
        )
