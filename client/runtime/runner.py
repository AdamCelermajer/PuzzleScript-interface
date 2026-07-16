from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event
from typing import Callable, Optional

from client.arc.base_env import BaseEnv
from client.arc.types import FrameData, GameAction, GameState
from client.engine.memory import EngineMemory
from client.engine.perception import EngineState
from client.engine.planner import DEFAULT_ACTIONS, PlanDecision
from client.engine.rulebook import Rulebook


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


@dataclass(frozen=True)
class RunResult:
    status: str
    reason: str
    steps: int
    game_id: str
    final_state: EngineState | None = None


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
        after_state = (
            self.perceiver.perceive_state(after_frame)
            if hasattr(self.perceiver, "perceive_state")
            else self.perceiver.perceive(after_frame)
        )
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
    if decision_reason == "rule_plan":
        return (
            f"Action: {action.name} "
            f"(rule plan, plan_steps={len(plan)}, predictions={predictions})"
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
        engine_or_perceiver,
        memory: EngineMemory | None = None,
        rulebook: Rulebook | None = None,
        planner=None,
        inducer=None,
        action_executor: ActionExecutor | None = None,
        *,
        dashboard=None,
        event_sink: Optional[Callable[[str], None]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        stop_event: Event | None = None,
    ) -> None:
        self.env = env
        self.dashboard = dashboard
        self.event_sink = event_sink
        self.sleep_fn = sleep_fn
        self.stop_event = stop_event or Event()
        self.engine = (
            engine_or_perceiver
            if hasattr(engine_or_perceiver, "action_selector")
            else None
        )
        if self.engine is not None:
            self.perceiver = self.engine.perceiver
            self.memory = self.engine.memory
            self.rulebook = self.engine.logical_rulebook
            self.planner = self.engine.planner
            self.inducer = self.engine.rule_learner
            self.action_selector = self.engine.action_selector
            self.goal_manager = self.engine.goal_manager
        else:
            self.perceiver = engine_or_perceiver
            if memory is None or rulebook is None or planner is None or inducer is None:
                raise ValueError("Legacy loop construction requires all engine modules")
            self.memory = memory
            self.rulebook = rulebook
            self.planner = planner
            self.inducer = inducer
            self.action_selector = None
            self.goal_manager = None
        self.action_executor = action_executor or ActionExecutor(env, self.perceiver)

    def request_stop(self) -> None:
        self.stop_event.set()

    def run(self, *, max_steps: int, game_id: str) -> RunResult:
        try:
            frame_data = self.env.reset()
        except Exception as exc:
            emit(f"Failed to initialize environment: {exc}", self.event_sink)
            return RunResult("failed", str(exc), 0, game_id)

        if hasattr(self.perceiver, "initial_perception"):
            current_state, self.legend = self.perceiver.initial_perception(frame_data)
        else:
            current_state = self.perceiver.perceive(frame_data)
            self.legend = dict(frame_data.legend or {})
        self.memory.append_state(current_state)
        actual_game_id = game_id or current_state.game_id
        task_goal = (
            self.goal_manager.define_task_goal(current_state, self.legend)
            if self.goal_manager is not None
            else None
        )
        steps = unchanged = 0
        emit(
            f"Started session {getattr(self.env, 'session_id', 'unknown')} in unified rule loop",
            self.event_sink,
        )
        emit(f"Legend: {self.legend}", self.event_sink)
        if task_goal is not None:
            emit(f"Task goal: {task_goal.description}", self.event_sink)
        set_dashboard(
            self.dashboard,
            status="Learning rules and solving from perceived transitions.",
            detail="Evidence store ready.",
        )

        while steps < max_steps:
            if self.stop_event.is_set():
                emit("Run stopped by request.", self.event_sink)
                return RunResult(
                    "cancelled", "stop_requested", steps, actual_game_id, current_state
                )
            if task_goal is not None and task_goal.reached_by(current_state):
                return RunResult(
                    "completed", "task_goal_reached", steps, actual_game_id, current_state
                )

            decision = self._choose_action(current_state, frame_data, task_goal)
            predictions = list(getattr(decision, "predictions", ())) or self.rulebook.predict(
                current_state, decision.action
            )
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

            outcome = self.action_executor.execute(frame_data, current_state, decision)
            contradicted = bool(predictions) and outcome.after_state not in predictions
            unexplained = not predictions
            _transition, contradicted_rule_ids = self._record_outcome(
                outcome, predictions, decision
            )
            self._handle_plan_validity(decision, contradicted, unexplained)
            learning_result = self._maybe_learn(
                actual_game_id,
                decision=decision,
                contradicted=contradicted,
                unexplained=unexplained,
                contradicted_rule_ids=contradicted_rule_ids,
            )
            if learning_result == "stop_required":
                emit("Stopped after repeated rule-learning failures.", self.event_sink)
                return RunResult(
                    "failed",
                    "repeated_rule_learning_failures",
                    steps + 1,
                    actual_game_id,
                    outcome.after_state,
                )
            if learning_result == "cancelled" or self.stop_event.is_set():
                emit("Run stopped by request.", self.event_sink)
                return RunResult(
                    "cancelled",
                    "stop_requested",
                    steps + 1,
                    actual_game_id,
                    outcome.after_state,
                )

            steps += 1
            frame_data = outcome.after_frame
            current_state = outcome.after_state

            if outcome.before_frame.frame == outcome.after_frame.frame:
                emit("Warning: Board state unchanged", self.event_sink)
                unchanged += 1
                if unchanged >= 3:
                    emit("Stuck - forcing reset", self.event_sink)
                    frame_data = self.env.reset()
                    current_state = self.perceiver.perceive_state(frame_data)
                    self.memory.append_state(current_state)
                    unchanged = 0
                    if self.action_selector is not None:
                        self.action_selector.invalidate_active_plan()
                    set_dashboard(
                        self.dashboard,
                        detail="Board reset after repeated unchanged moves.",
                    )
                self._sleep()
                continue

            unchanged = 0
            if frame_data.state == GameState.WIN:
                emit("World completed successfully!", self.event_sink)
                return RunResult(
                    "completed", "task_goal_reached", steps, actual_game_id, current_state
                )
            if frame_data.state == GameState.GAME_OVER:
                emit("Game Over... Resetting", self.event_sink)
                frame_data = self.env.reset()
                current_state = self.perceiver.perceive_state(frame_data)
                self.memory.append_state(current_state)
                if self.action_selector is not None:
                    self.action_selector.invalidate_active_plan()
                set_dashboard(
                    self.dashboard,
                    detail="Board reset after GAME_OVER.",
                )
            elif (
                outcome.after_frame.levels_completed
                != outcome.before_frame.levels_completed
            ):
                emit("Level complete!", self.event_sink)
            self._sleep()

        emit("Max steps reached.", self.event_sink)
        return RunResult(
            "completed", "step_budget_exhausted", steps, actual_game_id, current_state
        )

    def run_learning(self, *, max_steps: int, game_id: str) -> RunResult:
        return self.run(max_steps=max_steps, game_id=game_id)

    def run_solving(self, *, max_steps: int) -> RunResult:
        return self.run(max_steps=max_steps, game_id="")

    def _choose_action(self, current_state, frame_data, task_goal) -> PlanDecision:
        if self.action_selector is not None:
            actions = [
                action
                for action in DEFAULT_ACTIONS
                if action in current_state.available_actions
                and action != GameAction.RESET
            ]
            if not actions:
                actions = [
                    action
                    for action in DEFAULT_ACTIONS
                    if action in frame_data.available_actions
                    and action != GameAction.RESET
                ]
            if not actions:
                raise ValueError("No available actions for action selector")
            return self.action_selector.choose_action(
                current_state, task_goal, actions, legend=self.legend
            )
        return self.planner.choose_action()

    def _handle_plan_validity(
        self, decision: PlanDecision, contradicted: bool, unexplained: bool
    ) -> None:
        if not (contradicted or (unexplained and not decision.exploratory)):
            return
        if self.action_selector is not None:
            self.action_selector.invalidate_active_plan()
        elif hasattr(self.planner, "clear_llm_plan"):
            self.planner.clear_llm_plan()

    def _maybe_learn(
        self,
        game_id: str,
        *,
        decision: PlanDecision,
        contradicted: bool,
        unexplained: bool,
        contradicted_rule_ids: list[str] | None = None,
    ) -> str:
        if not (contradicted or unexplained):
            return "not_needed"
        if self.engine is not None:
            if contradicted:
                return self.inducer.revise_from_memory(
                    contradicted_rule_ids or [],
                    self.memory,
                    should_stop=self.stop_event.is_set,
                    legend=self.legend,
                )
            return self.inducer.learn_from_memory(
                game_id,
                self.memory,
                should_stop=self.stop_event.is_set,
                legend=self.legend,
            )
        recent = self.memory.recent(1)
        if not recent:
            return "no_transition"
        try:
            rule_ids = self.inducer.propose_from_memory(game_id, self.memory)
        except (RuntimeError, AssertionError, ValueError) as exc:
            emit(f"Rule induction unavailable, skipping: {exc}", self.event_sink)
            return "learning_failed"
        if rule_ids:
            emit(f"Proposed {len(rule_ids)} logical rules.", self.event_sink)
        return "learning_complete"

    def _record_outcome(self, outcome: StepOutcome, predictions, decision: PlanDecision):
        prediction_rule_ids = self.rulebook.predicting_rule_ids(
            outcome.before_state, outcome.action, predictions
        )
        transition = self.memory.append_action_result(
            outcome.action,
            outcome.after_state,
            predictions=predictions,
            prediction_rule_ids=prediction_rule_ids,
            decision_source=decision.source,
            prediction_recorded=True,
        )
        contradicted_rule_ids = self.rulebook.record_prediction_result(
            outcome.before_state,
            outcome.action,
            outcome.after_state,
            predictions,
            prediction_rule_ids=prediction_rule_ids,
            contradiction_id=transition.id,
        )
        return transition, contradicted_rule_ids

    def _sleep(self) -> None:
        if not self.stop_event.is_set():
            self.sleep_fn(1)
