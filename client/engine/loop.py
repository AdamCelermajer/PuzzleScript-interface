from __future__ import annotations

import time
from typing import Callable, Optional

from client.engine.actions import ActionExecutor, StepOutcome
from client.engine.base_env import BaseEnv
from client.engine.memory import EngineMemory
from client.engine.rulebook import EngineRulebook
from client.engine.types import FrameData, GameAction, GameState


HistoryEntry = tuple[FrameData, GameAction, FrameData]


def emit(message: str, event_sink: Optional[Callable[[str], None]] = None) -> None:
    (event_sink or print)(message)


def remember(history: list[HistoryEntry], entry: HistoryEntry) -> None:
    history.append(entry)
    del history[:-200]


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
    if decision_reason == "llm_subgoal":
        label = subgoal or "choose the next experiment"
        return (
            f"Action: {action.name} "
            f"(LLM subgoal: {label}, predictions={predictions})"
        )
    return f"Action: {action.name} ({decision_reason}, predictions={predictions})"


class RuleReasoningLoop:
    """Orchestrates receive, perceive, plan, act, and update modules."""

    def __init__(
        self,
        env: BaseEnv,
        perceiver,
        memory: EngineMemory,
        rulebook: EngineRulebook,
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
        self.history: list[HistoryEntry] = []

    def run_learning(
        self,
        *,
        max_steps: int,
        game_id: str,
        mode: str = "learn",
    ) -> None:
        try:
            frame_data = self.env.reset()
        except Exception as e:
            emit(f"Failed to initialize environment: {e}", self.event_sink)
            return

        current_state = self.perceiver.perceive(frame_data)
        steps = unchanged = last_induction_step = 0
        emit(
            f"Started session {getattr(self.env, 'session_id', 'unknown')} in LEARN mode",
            self.event_sink,
        )
        emit(f"Legend mapping from env: {frame_data.legend}", self.event_sink)
        set_dashboard(
            self.dashboard,
            status="Learning from perceived transitions.",
            detail="Evidence store ready.",
        )

        while True:
            if steps >= max_steps:
                emit("Max steps reached.", self.event_sink)
                return

            decision = self.planner.choose_action(current_state, frame_data)
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
            record = self._record_outcome(outcome, predictions)
            prediction_diverged = (
                bool(predictions) and outcome.after_state not in predictions
            )
            if prediction_diverged and hasattr(self.planner, "clear_llm_plan"):
                self.planner.clear_llm_plan()

            remember(self.history, (frame_data, decision.action, outcome.after_frame))
            frame_data = outcome.after_frame
            current_state = outcome.after_state

            if outcome.before_frame.frame == outcome.after_frame.frame:
                emit("Warning: Board state unchanged", self.event_sink)
                unchanged += 1
                if unchanged >= 3:
                    emit("Stuck - forcing reset", self.event_sink)
                    frame_data = self.env.reset()
                    current_state = self.perceiver.perceive(frame_data)
                    unchanged = 0
                    set_dashboard(
                        self.dashboard,
                        detail="Board reset after repeated unchanged moves.",
                    )
                self.sleep_fn(1)
                continue

            unchanged = 0
            steps += 1
            if prediction_diverged:
                self._maybe_induce_rules(game_id)
                last_induction_step = steps
            elif steps and steps % 5 == 0 and steps != last_induction_step:
                self._maybe_induce_rules(game_id)
                last_induction_step = steps

            if (
                outcome.after_frame.state in {GameState.WIN, GameState.GAME_OVER}
                or outcome.after_frame.levels_completed
                != outcome.before_frame.levels_completed
            ):
                emit("Level complete!", self.event_sink)
                if mode == "win" and outcome.after_frame.state == GameState.WIN:
                    emit("World completed successfully!", self.event_sink)
                    return
                if outcome.after_frame.state == GameState.GAME_OVER:
                    emit("Game Over... Resetting", self.event_sink)
                    frame_data = self.env.reset()
                    current_state = self.perceiver.perceive(frame_data)
                    set_dashboard(
                        self.dashboard,
                        detail="Board reset after GAME_OVER.",
                    )

            self.sleep_fn(1)

    def run_solving(self, *, max_steps: int) -> None:
        frame_data = self.env.reset()
        current_state = self.perceiver.perceive(frame_data)
        steps = 0
        emit(
            f"Started session {getattr(self.env, 'session_id', 'unknown')} in SOLVE mode",
            self.event_sink,
        )
        set_dashboard(
            self.dashboard,
            status="Solving with verified engine rules.",
            detail="Evidence store ready.",
        )

        while steps < max_steps:
            decision = self.planner.choose_action(current_state, frame_data)
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
            if (
                predictions
                and outcome.after_state not in predictions
                and hasattr(self.planner, "clear_llm_plan")
            ):
                self.planner.clear_llm_plan()

            remember(self.history, (frame_data, decision.action, outcome.after_frame))
            steps += 1
            frame_data = outcome.after_frame
            current_state = outcome.after_state

            if outcome.after_frame.state == GameState.WIN:
                emit("Game completed successfully!", self.event_sink)
                return
            if outcome.after_frame.state == GameState.GAME_OVER:
                emit("Game Over encountered during solve.", self.event_sink)
                return
            self.sleep_fn(1)

        emit("Stopped after max solve steps.", self.event_sink)

    def _record_outcome(
        self, outcome: StepOutcome, predictions
    ):
        self.rulebook.record_prediction_result(
            outcome.before_state,
            outcome.action,
            outcome.after_state,
            predictions,
        )
        record = self.memory.record_transition(
            outcome.before_state,
            outcome.action,
            outcome.after_state,
        )
        self.rulebook.record_observed_transition(record)
        return record

    def _maybe_induce_rules(self, game_id: str) -> None:
        recent = self.memory.recent(5)
        if not recent:
            return
        try:
            hypotheses = self.inducer.propose_from_recent(game_id, recent)
        except RuntimeError as e:
            emit(f"LLM failure during rule induction, skipping: {e}", self.event_sink)
            return
        except AssertionError as e:
            emit(f"Rule induction unavailable, skipping: {e}", self.event_sink)
            return
        if hypotheses:
            emit(f"Proposed {len(hypotheses)} rule hypotheses.", self.event_sink)
