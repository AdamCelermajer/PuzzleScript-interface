from __future__ import annotations

from dataclasses import dataclass

from client.arc.types import GameAction
from client.engine.perception import EngineState


@dataclass(frozen=True)
class Goal:
    """State target the planner tries to satisfy."""

    description: str
    kind: str = "win"


class GoalManager:
    """Owns the active goal/subgoal selected on behalf of the planner."""

    def __init__(self) -> None:
        self.game_goal: Goal | None = None
        self.subgoal: Goal | None = None

    def ensure_goal(self, _memory) -> Goal:
        if self.game_goal is None:
            self.game_goal = Goal("complete the level", kind="game_goal")
        return self.game_goal

    def set_subgoal(self, description: str) -> Goal:
        self.subgoal = Goal(
            description or "choose the next experiment",
            kind="subgoal",
        )
        return self.subgoal

    def ask_for_subgoal_action(
        self,
        *,
        llm_client,
        current: EngineState,
        actions: list[GameAction],
        recent_events: str,
        known_rules_text: str,
        image_data_urls: list[str] | None = None,
    ) -> tuple[Goal, list[GameAction]]:
        system, prompt = self._subgoal_action_prompt(
            current=current,
            actions=actions,
            recent_events=recent_events,
            known_rules_text=known_rules_text,
            image_data_urls=image_data_urls or [],
        )
        data = self._call_json(
            llm_client,
            system,
            prompt,
            image_data_urls=image_data_urls,
        )
        plan = self._parse_action_plan(data, actions)
        goal = self.set_subgoal(str(data.get("subgoal", "")).strip())
        return goal, plan

    def clear(self) -> None:
        self.game_goal = None
        self.subgoal = None

    def _subgoal_action_prompt(
        self,
        *,
        current: EngineState,
        actions: list[GameAction],
        recent_events: str,
        known_rules_text: str,
        image_data_urls: list[str],
    ) -> tuple[str, str]:
        system = (
            "You guide an agent learning a grid puzzle by experiment. "
            f"The game is '{current.game_id}'. "
            "Verified rules could not produce a plan, so choose a small useful "
            "subgoal and one next action to learn more or move toward solving. "
            "Use only the available actions. "
            "Do not predict the next board or dump a full state. "
            'Output only JSON: {"subgoal": "one short sentence", "plan": ["ACTION1"]}'
        )
        image_note = ""
        if image_data_urls:
            image_note = "Rendered image context is attached.\n\n"
        prompt = (
            f"Current board:\n{self._rows(current)}\n\n"
            f"Available actions: {', '.join(action.name for action in actions)}\n\n"
            f"Known rule hypotheses:\n{known_rules_text or '- none'}\n\n"
            f"Recent evidence:\n{recent_events or '- none'}\n\n"
            f"{image_note}"
            "Choose the next subgoal and one-action plan. Output only JSON."
        )
        return system, prompt

    def _call_json(
        self,
        llm_client,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
    ) -> dict:
        return llm_client.call_json(
            system,
            prompt,
            image_data_urls=image_data_urls,
            purpose="subgoal/action",
        )

    def _parse_action_plan(
        self,
        data: dict,
        available_actions: list[GameAction],
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

    def _rows(self, state: EngineState) -> str:
        return "\n".join(state.rows())
