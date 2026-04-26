from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from client.engine.types import FrameData, GameAction
from client.live_sokoban_poc.model import ACTION_DELTAS, BoardState, add_pos
from client.live_sokoban_poc.rules import RuleModel, explain_rule


DEFAULT_RULE_FILE = (
    Path(__file__).resolve().parent
    / "output"
    / "ps_sokoban_basic_level1_live_rules.md"
)

ACTION_ORDER = [
    GameAction.ACTION1,
    GameAction.ACTION2,
    GameAction.ACTION3,
    GameAction.ACTION4,
]


@dataclass
class LiveRunResult:
    solved: bool
    steps: int
    rule_file: Path
    actions: list[GameAction] = field(default_factory=list)


class LiveSokobanController:
    def __init__(
        self,
        env,
        *,
        output_path: str | Path = DEFAULT_RULE_FILE,
        event_sink: Callable[[str], None] | None = None,
        step_delay: float = 0.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.env = env
        self.output_path = Path(output_path)
        self.model = RuleModel(output_path=self.output_path)
        self.event_sink = event_sink or print
        self.step_delay = step_delay
        self.sleeper = sleeper
        self.steps = 0
        self.actions: list[GameAction] = []

    def run(self, *, max_steps: int = 120) -> LiveRunResult:
        frame = self.env.reset()
        board = BoardState.from_frame_data(frame)
        self._log("LIVE POC started with an empty prediction model.")

        board = self._discover_core_rules(board, max_steps=max_steps)
        frame = self.env.reset()
        board = BoardState.from_frame_data(frame)
        self._log("Discovery phase complete. Resetting to solve with learned rules.")

        while self.steps < max_steps:
            if self._is_solved(board, frame):
                return self._finish(True)

            plan = self._plan_to_goal(board)
            if not plan:
                plan = self._plan_to_unmodeled_action(board)
            if not plan:
                frame = self.env.reset()
                board = BoardState.from_frame_data(frame)
                self._log("No useful experiment reachable. Resetting to explore again.")
                plan = self._plan_to_unmodeled_action(board)
            if not plan:
                plan = [self._choose_exploration_action(board)]

            if plan:
                for action in plan:
                    board, frame = self._execute_and_learn(board, action)
                    if self._is_solved(board, frame):
                        return self._finish(True)
                    if self.steps >= max_steps:
                        return self._finish(False)
                continue

        return self._finish(False)

    def _discover_core_rules(self, board: BoardState, *, max_steps: int) -> BoardState:
        while self.steps < max_steps and not self._has_core_rules():
            action = self._choose_exploration_action(board)
            board, _ = self._execute_and_learn(board, action)
        return board

    def _execute_and_learn(
        self, board: BoardState, action: GameAction
    ) -> tuple[BoardState, FrameData]:
        prediction = self.model.predict(board, action)
        frame = self.env.step(action)
        actual = BoardState.from_frame_data(frame)
        self.steps += 1
        self.actions.append(action)

        if prediction is None:
            self.model.failures.append(
                f"exploration predicted False for {action.name} from player {board.player}"
            )
            rule = self.model.learn_from_transition(board, action, actual)
            self._log(f"explore {action.name}: created {rule.rule_id} ({rule.effect})")
            self._log(f"Rule {rule.rule_id} means: {explain_rule(rule)}")
            self._sleep_between_moves()
            return actual, frame

        if not self._is_solved(actual, frame) and prediction.board != actual:
            faulty_rule = self.model.rules[prediction.rule_id]
            revised = self.model.revise_after_failure(
                faulty_rule, board, action, actual
            )
            self._log(
                f"prediction failure on {action.name}: revised "
                f"{faulty_rule.rule_id} -> {revised.rule_id}"
            )
            self._log(f"Rule {revised.rule_id} means: {explain_rule(revised)}")
            self._sleep_between_moves()
            return actual, frame

        self.model.record_success(prediction.rule_id, board, action, actual)
        self._log(f"predict {action.name}: {prediction.rule_id} matched")
        self._sleep_between_moves()
        return actual, frame

    def _choose_exploration_action(self, board: BoardState) -> GameAction:
        effects = {rule.effect for rule in self.model.active_rules}

        for action in ACTION_ORDER:
            if self.model.predict(board, action) is None and self._would_observe_push(
                board, action
            ):
                return action

        for action in ACTION_ORDER:
            if self.model.predict(board, action) is None and self._would_observe_move(
                board, action
            ):
                return action

        for action in ACTION_ORDER:
            if self.model.predict(board, action) is None and self._would_observe_block(
                board, action
            ):
                return action

        if "blocked" not in effects:
            for action in ACTION_ORDER:
                if self._would_observe_block(board, action):
                    return action

        return ACTION_ORDER[self.steps % len(ACTION_ORDER)]

    def _has_core_rules(self) -> bool:
        effects = {rule.effect for rule in self.model.active_rules}
        return {"blocked", "move_player", "push_crate"}.issubset(effects)

    def _plan_to_goal(self, start: BoardState) -> list[GameAction]:
        queue: deque[tuple[BoardState, list[GameAction]]] = deque([(start, [])])
        seen = {self._state_key(start)}

        while queue:
            board, path = queue.popleft()
            if board.is_goal():
                return path
            for action in ACTION_ORDER:
                prediction = self.model.predict(board, action)
                if prediction is None:
                    continue
                next_board = prediction.board
                if next_board == board:
                    continue
                key = self._state_key(next_board)
                if key in seen:
                    continue
                seen.add(key)
                queue.append((next_board, [*path, action]))
        return []

    def _plan_to_unmodeled_action(self, start: BoardState) -> list[GameAction]:
        queue: deque[tuple[BoardState, list[GameAction]]] = deque([(start, [])])
        seen = {self._state_key(start)}
        best_candidate: tuple[int, list[GameAction]] | None = None

        while queue:
            board, path = queue.popleft()
            for action in ACTION_ORDER:
                prediction = self.model.predict(board, action)
                if prediction is None:
                    priority = self._unmodeled_action_priority(board, action)
                    if priority is not None:
                        candidate = (priority, [*path, action])
                        if priority == 0:
                            return candidate[1]
                        if best_candidate is None or (
                            priority,
                            len(candidate[1]),
                        ) < (best_candidate[0], len(best_candidate[1])):
                            best_candidate = candidate
                    continue
                next_board = prediction.board
                if next_board == board:
                    continue
                key = self._state_key(next_board)
                if key in seen:
                    continue
                seen.add(key)
                queue.append((next_board, [*path, action]))
        return best_candidate[1] if best_candidate else []

    def _is_solved(self, board: BoardState, frame: FrameData) -> bool:
        return board.is_goal() or int(getattr(frame, "levels_completed", 0)) >= 1

    def _finish(self, solved: bool) -> LiveRunResult:
        self.model.write_rule_file(final=True)
        self._log(
            f"LIVE POC {'solved' if solved else 'stopped'} after {self.steps} steps. "
            f"Rule file: {self.output_path}"
        )
        return LiveRunResult(
            solved=solved,
            steps=self.steps,
            rule_file=self.output_path,
            actions=list(self.actions),
        )

    def _log(self, message: str) -> None:
        self.event_sink(message)

    def _sleep_between_moves(self) -> None:
        if self.step_delay > 0:
            self.sleeper(self.step_delay)

    def _state_key(self, board: BoardState) -> tuple[tuple[int, int], tuple[tuple[int, int], ...]]:
        return board.player, tuple(sorted(board.crates))

    def _would_observe_move(self, board: BoardState, action: GameAction) -> bool:
        front = add_pos(board.player, ACTION_DELTAS[action])
        return board.is_inside(front) and front not in board.walls and front not in board.crates

    def _would_observe_push(self, board: BoardState, action: GameAction) -> bool:
        delta = ACTION_DELTAS[action]
        front = add_pos(board.player, delta)
        behind = add_pos(front, delta)
        return front in board.crates and not board.is_blocked(behind)

    def _would_observe_block(self, board: BoardState, action: GameAction) -> bool:
        delta = ACTION_DELTAS[action]
        front = add_pos(board.player, delta)
        behind = add_pos(front, delta)
        return (
            front in board.walls
            or not board.is_inside(front)
            or (front in board.crates and board.is_blocked(behind))
        )

    def _would_observe_interesting_change(
        self, board: BoardState, action: GameAction
    ) -> bool:
        return (
            self._would_observe_push(board, action)
            or self._would_observe_move(board, action)
            or self._would_observe_block(board, action)
        )

    def _unmodeled_action_priority(
        self, board: BoardState, action: GameAction
    ) -> int | None:
        if self._would_observe_push(board, action):
            return 0
        if self._would_observe_move(board, action):
            return 1
        if self._would_observe_block(board, action):
            return 2
        return None
