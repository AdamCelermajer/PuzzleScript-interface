from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from client.arc.base_env import BaseEnv
from client.arc.types import FrameData, GameAction, GameState
from client.engine.memory import EngineMemory
from client.engine.planner import PlanDecision
from client.engine.rulebook import Rulebook
from client.engine.perception import EngineState


@dataclass(frozen=True)
class StepOutcome:
    """Result of executing one chosen action against the real environment."""

    before_frame: FrameData
    before_state: EngineState
    decision: PlanDecision
    after_frame: FrameData
    after_state: EngineState

    @property
    def action(self) -> GameAction:
        return self.decision.action


class ActionExecutor:
    """Runtime boundary that applies an engine decision to the environment."""

    def __init__(self, env: BaseEnv, perceiver) -> None:
        self.env = env
        self.perceiver = perceiver

    def execute(
        self,
        before_frame: FrameData,
        before_state: EngineState,
        decision: PlanDecision,
    ) -> StepOutcome:
        after_frame = self.env.step(decision.action)
        after_state = self.perceiver.perceive(after_frame)
        return StepOutcome(
            before_frame=before_frame,
            before_state=before_state,
            decision=decision,
            after_frame=after_frame,
            after_state=after_state,
        )


def emit(message: str, event_sink: Optional[Callable[[str], None]] = None) -> None:
    (event_sink or print)(message)


def set_dashboard(
    dashboard, *, status: str | None = None, detail: str | None = None
) -> None:
    if dashboard is None:
        return
    if status is not None:
        dashboard.set_status(status)
    if detail is not None:
        dashboard.set_detail(detail)


def format_action_event(
    action: GameAction,
    decision_reason: str,
    plan: list[GameAction],
    predictions: int,
    subgoal: str = "",
) -> str:
    if decision_reason == "verified_plan":
        return (
            f"Action: {action.name} "
            f"(verified plan, plan_steps={len(plan)}, predictions={predictions})"
        )
    if decision_reason == "explore_subgoal":
        label = subgoal or "choose the next experiment"
        return (
            f"Action: {action.name} "
            f"(LLM subgoal: {label}, predictions={predictions})"
        )
    return f"Action: {action.name} ({decision_reason}, predictions={predictions})"


class RuleReasoningLoop:
    """Runtime orchestration around the engine's reasoning modules."""

    def __init__(
        self,
        env: BaseEnv,
        perceiver,
        memory: EngineMemory,
        rulebook: Rulebook,
        planner,
        inducer,
        action_executor: ActionExecutor | None = None,
        *,
        dashboard=None,
        event_sink: Optional[Callable[[str], None]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.env = env
        self.perceiver = perceiver
        self.memory = memory
        self.rulebook = rulebook
        self.planner = planner
        self.inducer = inducer
        self.action_executor = action_executor or ActionExecutor(env, perceiver)
        self.dashboard = dashboard
        self.event_sink = event_sink
        self.sleep_fn = sleep_fn

    def run(
        self,
        *,
        max_steps: int,
        game_id: str,
    ) -> None:
        try:
            frame_data = self.env.reset()
        except Exception as e:
            emit(f"Failed to initialize environment: {e}", self.event_sink)
            return

        current_state = self.perceiver.perceive(frame_data)
        self.memory.append_state(current_state)
        actual_game_id = game_id or current_state.game_id
        steps = unchanged = 0
        emit(
            f"Started session {getattr(self.env, 'session_id', 'unknown')} in unified rule loop",
            self.event_sink,
        )
        emit(f"Legend mapping from env: {frame_data.legend}", self.event_sink)
        set_dashboard(
            self.dashboard,
            status="Learning rules and solving from perceived transitions.",
            detail="Evidence store ready.",
        )

        while True:
            if steps >= max_steps:
                emit("Max steps reached.", self.event_sink)
                return

            decision = self.planner.choose_action()
            predictions = self.rulebook.predict(current_state, decision.action)
            emit(
                format_action_event(
                    decision.action,
                    decision.reason,
                    decision.plan,
                    len(predictions),
                    decision.subgoal,
                ),
                self.event_sink,
            )

            outcome = self.action_executor.execute(
                frame_data, current_state, decision
            )
            self._record_outcome(outcome, predictions)
            unexplained = not predictions or outcome.after_state not in predictions
            if unexplained:
                self.planner.clear_llm_plan()
            if decision.exploratory or unexplained:
                self._maybe_induce_rules(actual_game_id)

            steps += 1
            frame_data = outcome.after_frame
            current_state = outcome.after_state

            if outcome.before_frame.frame == outcome.after_frame.frame:
                emit("Warning: Board state unchanged", self.event_sink)
                unchanged += 1
                if unchanged >= 3:
                    emit("Stuck - forcing reset", self.event_sink)
                    frame_data = self.env.reset()
                    current_state = self.perceiver.perceive(frame_data)
                    self.memory.append_state(current_state)
                    unchanged = 0
                    set_dashboard(
                        self.dashboard,
                        detail="Board reset after repeated unchanged moves.",
                    )
                self.sleep_fn(1)
                continue

            unchanged = 0

            if (
                outcome.after_frame.state in {GameState.WIN, GameState.GAME_OVER}
                or outcome.after_frame.levels_completed
                != outcome.before_frame.levels_completed
            ):
                emit("Level complete!", self.event_sink)
                if outcome.after_frame.state == GameState.WIN:
                    emit("World completed successfully!", self.event_sink)
                    return
                if outcome.after_frame.state == GameState.GAME_OVER:
                    emit("Game Over... Resetting", self.event_sink)
                    frame_data = self.env.reset()
                    current_state = self.perceiver.perceive(frame_data)
                    self.memory.append_state(current_state)
                    set_dashboard(
                        self.dashboard,
                        detail="Board reset after GAME_OVER.",
                    )

            self.sleep_fn(1)

    def run_learning(
        self,
        *,
        max_steps: int,
        game_id: str,
    ) -> None:
        self.run(max_steps=max_steps, game_id=game_id)

    def run_solving(self, *, max_steps: int) -> None:
        self.run(max_steps=max_steps, game_id="")

    def _record_outcome(self, outcome: StepOutcome, predictions):
        self.rulebook.record_prediction_result(
            outcome.before_state,
            outcome.action,
            outcome.after_state,
            predictions,
        )
        record = self.memory.append_action_result(outcome.action, outcome.after_state)
        self.rulebook.record_transition(record)
        return record

    def _maybe_induce_rules(
        self,
        game_id: str,
    ) -> None:
        recent = self.memory.recent(1)
        if not recent:
            return
        try:
            hypotheses = self.inducer.propose_from_memory(game_id, self.memory)
        except RuntimeError as e:
            emit(f"LLM failure during rule induction, skipping: {e}", self.event_sink)
            return
        except AssertionError as e:
            emit(f"Rule induction unavailable, skipping: {e}", self.event_sink)
            return
        if hypotheses:
            emit(f"Proposed {len(hypotheses)} rule hypotheses.", self.event_sink)
