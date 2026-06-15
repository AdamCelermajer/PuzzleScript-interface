from __future__ import annotations

import json
import inspect
from collections import deque
from dataclasses import dataclass

from client.engine import prompts
from client.engine.history import TransitionHistory
from client.engine.rules import RuleLibrary
from client.engine.state import EngineState
from client.engine.types import FrameData, GameAction
from client.engine.utils import extract_json


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


class Planner:
    """Plans over verified transitions and explores when no plan is known."""

    def __init__(
        self,
        library: RuleLibrary,
        history: TransitionHistory,
        llm_client=None,
        max_depth: int = 20,
        node_limit: int = 200,
    ) -> None:
        self.library = library
        self.history = history
        self.llm_client = llm_client
        self.max_depth = max_depth
        self.node_limit = node_limit
        self.pending_llm_plan: list[GameAction] = []
        self.pending_llm_subgoal = ""

    def choose_action(
        self, current: EngineState, frame_data: FrameData
    ) -> PlanDecision:
        actions = self.available_actions(frame_data)
        plan = self.plan_to_win(current, actions)
        if plan:
            self.clear_llm_plan()
            return PlanDecision(plan[0], "verified_plan", plan)

        while self.pending_llm_plan:
            action = self.pending_llm_plan.pop(0)
            if action not in actions:
                continue
            return PlanDecision(
                action,
                "llm_subgoal",
                [action, *self.pending_llm_plan],
                subgoal=self.pending_llm_subgoal,
            )

        return self.ask_llm_for_subgoal(current, actions, frame_data)

    def clear_llm_plan(self) -> None:
        self.pending_llm_plan = []
        self.pending_llm_subgoal = ""

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
                for predicted in self.library.predict(state, action):
                    if predicted in seen:
                        continue
                    seen.add(predicted)
                    queue.append((predicted, [*path, action]))
        return None

    def available_actions(self, frame_data: FrameData) -> list[GameAction]:
        available = list(getattr(frame_data, "available_actions", []) or [])
        actions = [
            action
            for action in DEFAULT_ACTIONS
            if action in available and action != GameAction.RESET
        ]
        return actions or [
            GameAction.ACTION1,
            GameAction.ACTION2,
            GameAction.ACTION3,
            GameAction.ACTION4,
        ]

    def ask_llm_for_subgoal(
        self,
        current: EngineState,
        actions: list[GameAction],
        frame_data: FrameData,
    ) -> PlanDecision:
        if self.llm_client is None:
            raise RuntimeError(
                "Planner needs an LLM client when no verified plan exists"
            )

        image_data_urls = self._image_data_urls(frame_data)
        system, prompt = prompts.get_explore_subgoal_prompt(
            current_board="\n".join(current.rows()),
            available_actions=", ".join(action.name for action in actions),
            recent_events=self._recent_events_text(),
            known_rules_text=self.library.known_rules_text(),
            game_name=current.game_id,
            rendered_image_note=(
                "attached as current visual observation."
                if image_data_urls
                else ""
            ),
        )
        data = self._call_json(system, prompt, image_data_urls=image_data_urls)
        plan = self._parse_action_plan(data, actions)
        self.pending_llm_plan = plan[1:]
        self.pending_llm_subgoal = str(data.get("subgoal", "")).strip()
        return PlanDecision(
            plan[0],
            "llm_subgoal",
            plan,
            subgoal=self.pending_llm_subgoal,
        )

    def _call_json(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
    ) -> dict:
        if hasattr(self.llm_client, "call_json"):
            call_json = self.llm_client.call_json
            try:
                signature = inspect.signature(call_json)
            except (TypeError, ValueError):
                signature = None
            if signature is None or "image_data_urls" in signature.parameters:
                return call_json(
                    system,
                    prompt,
                    model_type="flash",
                    image_data_urls=image_data_urls,
                )
            return call_json(system, prompt, model_type="flash")
        call = self.llm_client._call
        try:
            signature = inspect.signature(call)
        except (TypeError, ValueError):
            signature = None
        kwargs = {"model_type": "flash", "json_mode": True}
        if signature is None or "image_data_urls" in signature.parameters:
            kwargs["image_data_urls"] = image_data_urls
        response = call(system, prompt, **kwargs)
        return json.loads(extract_json(response))

    def _image_data_urls(self, frame_data: FrameData) -> list[str]:
        rendered_frame = getattr(frame_data, "rendered_frame", None)
        data_url = getattr(rendered_frame, "data_url", "")
        if not data_url:
            return []
        return [str(data_url)]

    def _parse_action_plan(
        self, data: dict, available_actions: list[GameAction]
    ) -> list[GameAction]:
        raw_plan = data.get("plan") or data.get("actions")
        if raw_plan is None and data.get("action"):
            raw_plan = [data["action"]]
        if not isinstance(raw_plan, list):
            raise ValueError(f"LLM exploration response has no action plan: {data}")

        plan: list[GameAction] = []
        for value in raw_plan:
            name = str(value).strip().upper()
            if name not in GameAction.__members__:
                raise ValueError(f"LLM returned unknown action: {value}")
            action = GameAction[name]
            if action not in available_actions:
                raise ValueError(
                    f"LLM returned unavailable action {action.name}; "
                    f"available: {', '.join(item.name for item in available_actions)}"
                )
            plan.append(action)

        if not plan:
            raise ValueError(f"LLM exploration response has empty plan: {data}")
        return plan

    def _recent_events_text(self) -> str:
        lines = []
        for record in self.history.recent(5):
            lines.append(
                f"{record.id}: {record.action.name}\n"
                f"Before:\n{self._rows(record.before)}\n"
                f"After:\n{self._rows(record.after)}"
            )
        return "\n\n".join(lines)

    def _rows(self, state: EngineState) -> str:
        return "\n".join(state.rows())
