import time
from typing import Callable, Optional

from client.engine.architecture import EngineArchitecture
from client.engine.base_env import BaseEnv
from client.engine.llm_client import Config, LlmClient
from client.engine.types import FrameData, GameAction, GameState


HistoryEntry = tuple[FrameData, GameAction, FrameData]


def _emit(message: str, event_sink: Optional[Callable[[str], None]] = None) -> None:
    (event_sink or print)(message)


def _remember(history: list[HistoryEntry], entry: HistoryEntry) -> None:
    history.append(entry)
    del history[:-200]


def _set_dashboard(
    dashboard, *, status: str | None = None, detail: str | None = None
) -> None:
    if dashboard is None:
        return
    if status is not None:
        dashboard.set_status(status)
    if detail is not None:
        dashboard.set_detail(detail)


def _format_action_event(
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


class Agent:
    """Readable orchestrator for the perceived transition engine."""

    def __init__(
        self,
        config: Config,
        llm_client: LlmClient,
        event_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize the engine loop state."""
        self.cfg = config
        self.llm_client = llm_client
        self.event_sink = event_sink
        self.history: list[HistoryEntry] = []
        self.engine = EngineArchitecture.from_config(
            self.cfg, self.llm_client, event_sink=self.event_sink
        )


def _record_engine_transition(
    agent: Agent,
    before_state,
    action: GameAction,
    next_frame: FrameData,
    predictions,
):
    after_state = agent.engine.perceiver.perceive(next_frame)
    agent.engine.library.record_prediction_result(
        before_state, action, after_state, predictions
    )
    record = agent.engine.history.add(before_state, action, after_state)
    agent.engine.library.record_transition(record)
    return record, after_state


def _maybe_induce_engine_rules(
    cfg: Config,
    agent: Agent,
    event_sink: Optional[Callable[[str], None]],
) -> None:
    recent = agent.engine.history.recent(5)
    if not recent:
        return
    try:
        hypotheses = agent.engine.inducer.propose_from_recent(cfg.game, recent)
    except RuntimeError as e:
        _emit(f"LLM failure during rule induction, skipping: {e}", event_sink)
        return
    except AssertionError as e:
        _emit(f"Rule induction unavailable, skipping: {e}", event_sink)
        return
    if hypotheses:
        _emit(f"Proposed {len(hypotheses)} rule hypotheses.", event_sink)


def run_learning_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    try:
        frame_data = env.reset()
    except Exception as e:
        _emit(f"Failed to initialize environment: {e}", event_sink)
        return

    current_state = agent.engine.perceiver.perceive(frame_data)
    steps = unchanged = last_induction_step = 0
    _emit(
        f"Started session {getattr(env, 'session_id', 'unknown')} in LEARN mode",
        event_sink,
    )
    _emit(f"Legend mapping from env: {frame_data.legend}", event_sink)
    _set_dashboard(
        dashboard,
        status="Learning from perceived transitions.",
        detail=f"Evidence store: {agent.engine.base_path}",
    )

    while True:
        if steps >= cfg.max_steps:
            _emit("Max steps reached.", event_sink)
            return

        decision = agent.engine.planner.choose_action(current_state, frame_data)
        action = decision.action
        predictions = agent.engine.library.predict(current_state, action)
        _emit(
            _format_action_event(
                action,
                decision.reason,
                decision.plan,
                len(predictions),
                decision.subgoal,
            ),
            event_sink,
        )

        prev_frame, next_frame = frame_data, env.step(action)
        _record, next_state = _record_engine_transition(
            agent, current_state, action, next_frame, predictions
        )
        prediction_diverged = bool(predictions) and next_state not in predictions
        if prediction_diverged:
            agent.engine.planner.clear_llm_plan()
        frame_data = next_frame
        current_state = next_state
        entry = (prev_frame, action, next_frame)
        _remember(agent.history, entry)

        if prev_frame.frame == next_frame.frame:
            _emit("Warning: Board state unchanged", event_sink)
            unchanged += 1
            if unchanged >= 3:
                _emit("Stuck - forcing reset", event_sink)
                frame_data = env.reset()
                current_state = agent.engine.perceiver.perceive(frame_data)
                unchanged = 0
                _set_dashboard(
                    dashboard, detail="Board reset after repeated unchanged moves."
                )
            time.sleep(1)
            continue

        unchanged = 0
        steps += 1
        if prediction_diverged:
            _maybe_induce_engine_rules(cfg, agent, event_sink)
            last_induction_step = steps
        elif steps and steps % 5 == 0 and steps != last_induction_step:
            _maybe_induce_engine_rules(cfg, agent, event_sink)
            last_induction_step = steps

        if (
            next_frame.state in {GameState.WIN, GameState.GAME_OVER}
            or next_frame.levels_completed != prev_frame.levels_completed
        ):
            _emit("Level complete!", event_sink)
            if cfg.mode == "win" and next_frame.state == GameState.WIN:
                _emit("World completed successfully!", event_sink)
                return
            if next_frame.state == GameState.GAME_OVER:
                _emit("Game Over... Resetting", event_sink)
                frame_data = env.reset()
                current_state = agent.engine.perceiver.perceive(frame_data)
                _set_dashboard(dashboard, detail="Board reset after GAME_OVER.")

        time.sleep(1)


def run_solving_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    frame_data = env.reset()
    current_state = agent.engine.perceiver.perceive(frame_data)
    steps = 0
    _emit(
        f"Started session {getattr(env, 'session_id', 'unknown')} in SOLVE mode",
        event_sink,
    )
    _set_dashboard(
        dashboard,
        status="Solving with verified engine rules.",
        detail=f"Evidence store: {agent.engine.base_path}",
    )

    while steps < cfg.max_steps:
        decision = agent.engine.planner.choose_action(current_state, frame_data)
        action = decision.action
        predictions = agent.engine.library.predict(current_state, action)
        _emit(
            _format_action_event(
                action,
                decision.reason,
                decision.plan,
                len(predictions),
                decision.subgoal,
            ),
            event_sink,
        )

        next_frame = env.step(action)
        _record, next_state = _record_engine_transition(
            agent, current_state, action, next_frame, predictions
        )
        if predictions and next_state not in predictions:
            agent.engine.planner.clear_llm_plan()
        _remember(agent.history, (frame_data, action, next_frame))
        steps += 1
        frame_data = next_frame
        current_state = next_state

        if next_frame.state == GameState.WIN:
            _emit("Game completed successfully!", event_sink)
            return
        if next_frame.state == GameState.GAME_OVER:
            _emit("Game Over encountered during solve.", event_sink)
            return
        time.sleep(1)

    _emit("Stopped after max solve steps.", event_sink)
