from __future__ import annotations

from dataclasses import dataclass

from client.arc.types import GameAction
from client.engine.legend import format_legend
from client.engine.perception import EngineState
from client.engine.prompts import PromptStore


@dataclass(frozen=True)
class Goal:
    """State target the planner tries to satisfy."""

    description: str
    kind: str = "win"

    def reached_by(self, state: EngineState) -> bool:
        return state.is_win()


class GoalManager:
    """Owns the active goal/subgoal selected on behalf of the planner."""

    def __init__(
        self,
        llm_client=None,
        *,
        provide_end_goal: bool = True,
        end_goal: str = "complete the level",
        prompt_store: PromptStore | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.provide_end_goal = provide_end_goal
        self.end_goal = end_goal.strip() or "complete the level"
        self.prompt_store = prompt_store or PromptStore()
        self.game_goal: Goal | None = None
        self.subgoal: Goal | None = None

    def ensure_goal(self, _memory) -> Goal:
        if self.game_goal is None:
            self.game_goal = Goal(self.end_goal, kind="game_goal")
        return self.game_goal

    def define_task_goal(
        self,
        state: EngineState,
        legend: dict[int, str] | None = None,
    ) -> Goal:
        if self.game_goal is not None:
            return self.game_goal
        if self.provide_end_goal:
            return self.ensure_goal(None)
        if self.llm_client is None:
            raise RuntimeError("GoalManager needs an LLM client to infer the task goal")
        images = [state.image.data_url] if state.image is not None else []
        data = self._call_json(
            self.llm_client,
            (
                f"{self.prompt_store.get('task_goal')}\n\n"
                'Output only JSON: {"goal": "one short sentence"}.'
            ),
            (
                f"Legend:\n{format_legend(legend)}\n\n"
                f"First board:\n{self._rows(state)}\n\n"
                "Infer the end goal. Output only JSON."
            ),
            image_data_urls=images,
            purpose="task goal",
        )
        description = str(data.get("goal", "")).strip()
        if not description:
            raise ValueError("LLM task-goal response has no goal")
        self.game_goal = Goal(description, kind="game_goal")
        return self.game_goal

    def choose_subgoal(
        self,
        *,
        current: EngineState,
        task_goal: Goal,
        actions: list[GameAction],
        memory,
        logical_rulebook,
        legend: dict[int, str] | None = None,
    ) -> Goal:
        if self.llm_client is None:
            raise RuntimeError("GoalManager needs an LLM client to choose a subgoal")
        events, images = memory.latest_visual_context()
        return self.ask_for_subgoal(
            llm_client=self.llm_client,
            current=current,
            actions=actions,
            recent_events=events,
            known_rules_text=logical_rulebook.known_rules_text(),
            image_data_urls=images,
            legend=legend,
        )

    def set_subgoal(self, description: str) -> Goal:
        self.subgoal = Goal(
            description or "choose the next experiment",
            kind="subgoal",
        )
        return self.subgoal

    def ask_for_subgoal(
        self,
        *,
        llm_client,
        current: EngineState,
        actions: list[GameAction],
        recent_events: str,
        known_rules_text: str,
        image_data_urls: list[str] | None = None,
        legend: dict[int, str] | None = None,
    ) -> Goal:
        system, prompt = self._subgoal_prompt(
            current=current,
            actions=actions,
            recent_events=recent_events,
            known_rules_text=known_rules_text,
            image_data_urls=image_data_urls or [],
            legend=legend,
        )
        data = self._call_json(
            llm_client,
            system,
            prompt,
            image_data_urls=image_data_urls,
            purpose="subgoal",
        )
        return self.set_subgoal(str(data.get("subgoal", "")).strip())

    def ask_for_action_plan(
        self,
        *,
        llm_client,
        current: EngineState,
        actions: list[GameAction],
        subgoal: Goal,
        recent_events: str,
        known_rules_text: str,
        image_data_urls: list[str] | None = None,
        legend: dict[int, str] | None = None,
    ) -> list[GameAction]:
        system, prompt = self._action_plan_prompt(
            current=current,
            actions=actions,
            subgoal=subgoal,
            recent_events=recent_events,
            known_rules_text=known_rules_text,
            image_data_urls=image_data_urls or [],
            legend=legend,
        )
        data = self._call_json(
            llm_client,
            system,
            prompt,
            image_data_urls=image_data_urls,
            purpose="action plan",
        )
        return self._parse_action_plan(data, actions)

    def clear(self) -> None:
        self.game_goal = None
        self.subgoal = None

    def _subgoal_prompt(
        self,
        *,
        current: EngineState,
        actions: list[GameAction],
        recent_events: str,
        known_rules_text: str,
        image_data_urls: list[str],
        legend: dict[int, str] | None,
    ) -> tuple[str, str]:
        system = (
            f"{self.prompt_store.get('subgoal')}\n\n"
            f"The game is '{current.game_id}'. "
            "Verified rules could not produce a plan, so choose one small useful "
            "subgoal to learn more or move toward solving. "
            'Output only JSON: {"subgoal": "one short sentence"}'
        )
        image_note = ""
        if image_data_urls:
            image_note = "Rendered image context is attached.\n\n"
        prompt = (
            f"Legend:\n{format_legend(legend)}\n\n"
            f"Current board:\n{self._rows(current)}\n\n"
            f"Available actions: {', '.join(action.name for action in actions)}\n\n"
            f"Known rule summaries:\n{known_rules_text or '- none'}\n\n"
            f"Recent evidence:\n{recent_events or '- none'}\n\n"
            f"{image_note}"
            "Choose the next subgoal. Output only JSON."
        )
        return system, prompt

    def _action_plan_prompt(
        self,
        *,
        current: EngineState,
        actions: list[GameAction],
        subgoal: Goal,
        recent_events: str,
        known_rules_text: str,
        image_data_urls: list[str],
        legend: dict[int, str] | None,
    ) -> tuple[str, str]:
        system = (
            f"{self.prompt_store.get('action_plan')}\n\n"
            f"The game is '{current.game_id}'. "
            "A separate step has already selected the current subgoal. "
            'Output only JSON: {"plan": ["ACTION1", "ACTION4"]}'
        )
        image_note = ""
        if image_data_urls:
            image_note = "Rendered image context is attached.\n\n"
        prompt = (
            f"Current subgoal: {subgoal.description}\n\n"
            f"Legend:\n{format_legend(legend)}\n\n"
            f"Current board:\n{self._rows(current)}\n\n"
            f"Available actions: {', '.join(action.name for action in actions)}\n\n"
            f"Known rule summaries:\n{known_rules_text or '- none'}\n\n"
            f"Recent evidence:\n{recent_events or '- none'}\n\n"
            f"{image_note}"
            "Choose a short action plan for the current subgoal. Output only JSON."
        )
        return system, prompt

    def _call_json(
        self,
        llm_client,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "action plan",
    ) -> dict:
        last_error = ""
        current_prompt = prompt
        for attempt in range(2):
            try:
                return llm_client.call_json(
                    system,
                    current_prompt,
                    image_data_urls=image_data_urls,
                    purpose=purpose,
                )
            except ValueError as exc:
                last_error = str(exc)
                if attempt == 0 and "invalid JSON" in last_error:
                    current_prompt = (
                        f"{prompt}\n\nThe previous response was not valid JSON. "
                        "Return only the required JSON object with no prose or fences."
                    )
                    continue
                raise
        raise ValueError(last_error or "LLM returned no JSON response")

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
