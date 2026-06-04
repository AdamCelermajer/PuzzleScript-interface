from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from client.engine.types import FrameData, GameAction

from .model import DEFAULT_SYMBOL_MAP, SymbolFrame, SymbolGoal
from .perceiver import SymbolPerceiver
from .rules import DEFAULT_OUTPUT_PATH, LiveRuleModel


DEFAULT_ACTIONS = (
    GameAction.ACTION1,
    GameAction.ACTION2,
    GameAction.ACTION3,
    GameAction.ACTION4,
)
PLANNING_DEPTH = 40
MAX_EXPERIMENT_STEPS = 40


class LiveEnv(Protocol):
    def reset(self) -> FrameData: ...

    def step(self, action: GameAction) -> FrameData: ...


@dataclass(frozen=True)
class LiveRunResult:
    goal_reached: bool
    steps: int
    actions: list[GameAction]
    final_frame: SymbolFrame
    output_path: Path


class LiveRunner:
    def __init__(
        self,
        env: LiveEnv,
        goal: SymbolGoal,
        output_path: str | Path | None = None,
        store_path: str | Path | None = None,
        journal_path: str | Path | None = None,
        compact_output_path: str | Path | None = None,
        model: LiveRuleModel | None = None,
        symbol_map: dict[int, str] | None = None,
        max_steps: int = 200,
        sleep_seconds: float = 0.0,
        event_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.env = env
        self.goal = goal
        self.perceiver = SymbolPerceiver(symbol_map or DEFAULT_SYMBOL_MAP)
        self.max_steps = min(int(max_steps), MAX_EXPERIMENT_STEPS)
        self.sleep_seconds = float(sleep_seconds)
        self.event_sink = event_sink or (lambda _message: None)
        self.model = model or LiveRuleModel(
            output_path or DEFAULT_OUTPUT_PATH,
            store_path=store_path,
            journal_path=journal_path,
            compact_output_path=compact_output_path,
        )
        if hasattr(self.model, "seed_target_positions"):
            self.model.seed_target_positions(self.goal.target_positions())
        self.actions_taken: list[GameAction] = []
        self.action_attempts: dict[tuple[SymbolFrame, GameAction], int] = {}

    def run(self) -> LiveRunResult:
        frame_data = self.env.reset()
        current = self.perceiver.perceive(frame_data)
        self._write_report(current=current, final=False)

        if self.goal.is_satisfied(current):
            return self._finish(True, 0, current)

        for step in range(1, self.max_steps + 1):
            action = self._choose_action(current, frame_data)
            predictions = self.model.predict(current, action)
            self._event(
                f"step {step}: executing {action.name}; predictions={len(predictions)}"
            )

            frame_data = self.env.step(action)
            next_frame = self.perceiver.perceive(frame_data)
            self.actions_taken.append(action)

            self.model.record_prediction_result(
                current, action, next_frame, predictions
            )
            self.model.observe(current, action, next_frame)
            self._mark_attempt(current, action)
            current = next_frame
            self._write_report(current=current, final=False)

            if self.goal.is_satisfied(current):
                return self._finish(True, step, current)

            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)

        return self._finish(False, self.max_steps, current)

    def _choose_action(self, current: SymbolFrame, frame_data: FrameData) -> GameAction:
        actions = self._available_actions(frame_data)

        plan = self._known_plan_to_goal(current, frame_data)
        if plan:
            self.model.record_explorer_selection(plan[0], "goal_plan")
            return plan[0]

        current_context = self.model.unseen_context_action(current, actions)
        if current_context is not None:
            action, context = current_context
            self.model.record_explorer_selection(
                action, "current_unseen_context", context
            )
            return action

        unprobed = self._unprobed_action(actions)
        if unprobed is not None:
            self.model.record_explorer_selection(unprobed, "unprobed_action")
            return unprobed

        reachable = self._plan_to_unseen_context(current, frame_data)
        if reachable:
            path, context = reachable
            action = path[0]
            self.model.record_explorer_selection(
                action, "reachable_unseen_context", context
            )
            return action

        fallback = min(
            actions,
            key=lambda action: (
                self.action_attempts.get((current, action), 0),
                actions.index(action),
            ),
        )
        self.model.record_explorer_selection(fallback, "least_tried_fallback")
        return fallback

    def _known_plan_to_goal(
        self, current: SymbolFrame, frame_data: FrameData
    ) -> list[GameAction] | None:
        actions = self._available_actions(frame_data)
        queue: deque[tuple[SymbolFrame, list[GameAction]]] = deque([(current, [])])
        seen = {current}

        while queue:
            frame, path = queue.popleft()
            if self.goal.is_satisfied(frame) and path:
                return path
            if len(path) >= PLANNING_DEPTH:
                continue
            for action in actions:
                for predicted in self.model.predict(frame, action):
                    if predicted in seen:
                        continue
                    seen.add(predicted)
                    queue.append((predicted, [*path, action]))
        return None

    def _plan_to_unseen_context(
        self, current: SymbolFrame, frame_data: FrameData
    ) -> tuple[list[GameAction], tuple] | None:
        actions = self._available_actions(frame_data)
        queue: deque[tuple[SymbolFrame, list[GameAction]]] = deque([(current, [])])
        seen = {current}

        while queue:
            frame, path = queue.popleft()
            target = self.model.unseen_context_action(frame, actions)
            if path and target:
                _target_action, context = target
                return path, context
            if len(path) >= PLANNING_DEPTH:
                continue
            for action in actions:
                for predicted in self.model.predict(frame, action):
                    if predicted in seen:
                        continue
                    seen.add(predicted)
                    queue.append((predicted, [*path, action]))
        return None

    def _available_actions(self, frame_data: FrameData) -> list[GameAction]:
        available = list(getattr(frame_data, "available_actions", []) or [])
        actions = [action for action in DEFAULT_ACTIONS if action in available]
        return actions or list(DEFAULT_ACTIONS)

    def _unprobed_action(self, actions: list[GameAction]) -> GameAction | None:
        for action in actions:
            if action in self.actions_taken:
                continue
            if not self.model.action_has_delta(action):
                return action
        return None

    def _mark_attempt(self, frame: SymbolFrame, action: GameAction) -> None:
        key = (frame, action)
        self.action_attempts[key] = self.action_attempts.get(key, 0) + 1

    def _finish(
        self, reached: bool, steps: int, current: SymbolFrame
    ) -> LiveRunResult:
        self._event("Goal reached." if reached else "Goal was not reached.")
        self._write_report(current=current, final=True, reached=reached)
        return LiveRunResult(
            goal_reached=reached,
            steps=steps,
            actions=list(self.actions_taken),
            final_frame=current,
            output_path=self.model.output_path,
        )

    def _write_report(
        self, current: SymbolFrame, final: bool, reached: bool | None = None
    ) -> None:
        sections = [
            "## Goal Facts",
            "",
            self.goal.to_markdown(),
            "",
            "## Current Symbol Frame",
            "",
            *[f"- `{row}`" for row in current.to_rows()],
            "",
            "## Current Percepts",
            "",
            *[
                f"- `{fact}`"
                for fact in current.facts(
                    known_target_positions=self.model.target_positions
                )
            ],
            "",
            "## Run Status",
            "",
        ]
        if reached is True:
            sections.append("- Goal reached.")
        elif reached is False:
            sections.append("- Goal was not reached.")
        else:
            sections.append("- Run in progress.")
        sections.append(f"- Actions executed: {[action.name for action in self.actions_taken]}")
        self.model.write(final=final, extra_sections=sections)

    def _event(self, message: str) -> None:
        self.event_sink(message)
