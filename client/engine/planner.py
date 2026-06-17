from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from client.engine.goal_manager import Goal, GoalManager
from client.engine.memory import EngineMemory
from client.engine.perception import EngineState
from client.engine.rulebook import Rulebook
from client.arc.types import FrameData, GameAction


DEFAULT_ACTIONS = (
    GameAction.ACTION1,
    GameAction.ACTION2,
    GameAction.ACTION3,
    GameAction.ACTION4,
    GameAction.ACTION5,
    GameAction.ACTION7,
)


@dataclass(frozen=True)
class PlanDecision:
    action: GameAction
    reason: str
    plan: list[GameAction]
    subgoal: str = ""
    exploratory: bool = False


@dataclass(frozen=True)
class ActivePlan:
    goal: Goal
    actions: tuple[GameAction, ...]
    index: int = 0

    def next_action(self) -> GameAction | None:
        if self.index >= len(self.actions):
            return None
        return self.actions[self.index]

    def advance(self) -> "ActivePlan":
        return ActivePlan(
            goal=self.goal,
            actions=self.actions,
            index=self.index + 1,
        )


class Planner:
    """Planner-first action router over memory, goals, and verified rules."""

    def __init__(
        self,
        rulebook: Rulebook | None = None,
        memory: EngineMemory | None = None,
        llm_client=None,
        goal_manager: GoalManager | None = None,
        max_depth: int = 20,
        node_limit: int = 200,
    ) -> None:
        if rulebook is None:
            raise ValueError("Planner requires a rulebook")
        self.rulebook = rulebook
        self.memory = memory
        self.llm_client = llm_client
        self.goal_manager = goal_manager or GoalManager()
        self.max_depth = max_depth
        self.node_limit = node_limit
        self.game_goal: Goal | None = None
        self.active_plan: ActivePlan | None = None

    def choose_action(
        self,
        current: EngineState | None = None,
        frame_data: FrameData | None = None,
    ) -> PlanDecision:
        memory = self.memory
        if current is None:
            if memory is None:
                raise ValueError("Planner needs memory or an explicit current state")
            current = memory.current_state()
        actions = self.available_actions(current, frame_data)

        continued = self._continue_active_plan(current)
        if continued is not None:
            return continued

        if self.game_goal is None:
            self.game_goal = self.goal_manager.ensure_goal(memory)

        planned = self.plan_to_goal(current, actions)
        if planned:
            self.active_plan = ActivePlan(
                goal=self.game_goal,
                actions=tuple(planned),
            )
            return PlanDecision(planned[0], "verified_plan", planned)

        return self.ask_llm_for_subgoal(
            current=current,
            actions=actions,
            frame_data=frame_data,
        )

    def clear_llm_plan(self) -> None:
        self.active_plan = None

    def plan_to_goal(
        self, current: EngineState, actions: list[GameAction]
    ) -> list[GameAction] | None:
        return self.plan_to_win(current, actions)

    def plan_to_win(
        self, current: EngineState, actions: list[GameAction]
    ) -> list[GameAction] | None:
        queue: deque[tuple[EngineState, list[GameAction]]] = deque([(current, [])])
        seen = {current}
        nodes = 0

        while queue:
            state, path = queue.popleft()
            nodes += 1
            if nodes > self.node_limit:
                return None
            if path and state.is_win():
                return path
            if len(path) >= self.max_depth:
                continue
            for action in actions:
                for predicted in self.rulebook.predict(state, action):
                    if predicted in seen:
                        continue
                    seen.add(predicted)
                    queue.append((predicted, [*path, action]))
        return None

    def available_actions(
        self, current: EngineState, frame_data: FrameData | None = None
    ) -> list[GameAction]:
        available = list(current.available_actions)
        if frame_data is not None:
            available = list(getattr(frame_data, "available_actions", []) or available)
        actions = [
            action
            for action in DEFAULT_ACTIONS
            if action in available and action != GameAction.RESET
        ]
        if not actions:
            raise ValueError("No available actions for planner")
        return actions

    def ask_llm_for_subgoal(
        self,
        current: EngineState,
        actions: list[GameAction],
        frame_data: FrameData | None = None,
    ) -> PlanDecision:
        if self.llm_client is None:
            raise RuntimeError(
                "Planner needs an LLM client when no verified plan exists"
            )

        recent_events, image_data_urls = self._prompt_context(current, frame_data)
        goal, plan = self.goal_manager.ask_for_subgoal_action(
            llm_client=self.llm_client,
            current=current,
            actions=actions,
            recent_events=recent_events,
            known_rules_text=self.rulebook.known_rules_text(),
            image_data_urls=image_data_urls,
        )
        self.active_plan = ActivePlan(goal, tuple(plan))
        return PlanDecision(
            plan[0],
            "explore_subgoal",
            [plan[0]],
            subgoal=goal.description,
            exploratory=True,
        )

    def _continue_active_plan(self, current: EngineState) -> PlanDecision | None:
        if self.active_plan is None:
            return None
        action = self.active_plan.next_action()
        if action is None:
            self.active_plan = None
            return None
        self.active_plan = self.active_plan.advance()
        return PlanDecision(action, "active_plan", [action])

    def _prompt_context(
        self,
        current: EngineState,
        frame_data: FrameData | None,
    ) -> tuple[str, list[str]]:
        if self.memory is not None:
            text, images = self.memory.latest_visual_context()
            if text or images:
                return text, images
        images = []
        if current.image is not None:
            images.append(current.image.data_url)
        elif frame_data is not None:
            rendered_frame = getattr(frame_data, "rendered_frame", None)
            data_url = getattr(rendered_frame, "data_url", "")
            if data_url:
                images.append(str(data_url))
        return self._recent_events_text(), images

    def _recent_events_text(self) -> str:
        if self.memory is None:
            return ""
        return self.memory.recent_context(limit=1)
