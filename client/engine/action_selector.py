from __future__ import annotations

from client.arc.types import GameAction
from client.engine.goal_manager import Goal, GoalManager
from client.engine.memory import EngineMemory
from client.engine.perception import EngineState
from client.engine.planner import ActivePlan, PlanDecision, RulePlanner
from client.engine.prompts import PromptStore
from client.engine.rulebook import Rulebook


class ProbePlanner:
    """Creates a short exploratory action plan for an already selected subgoal."""

    def __init__(
        self,
        llm_client,
        prompt_store: PromptStore | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_store = prompt_store

    def create_plan(
        self,
        *,
        state: EngineState,
        subgoal: Goal,
        actions: list[GameAction],
        memory: EngineMemory,
        logical_rulebook: Rulebook,
        legend: dict[int, str] | None = None,
    ) -> list[GameAction]:
        events, images = memory.latest_visual_context()
        manager = GoalManager(prompt_store=self.prompt_store)
        return manager.ask_for_action_plan(
            llm_client=self.llm_client,
            current=state,
            actions=actions,
            subgoal=subgoal,
            recent_events=events,
            known_rules_text=logical_rulebook.known_rules_text(),
            image_data_urls=images,
            legend=legend,
        )


class ActionSelector:
    """Routes the next action to an active plan, rule plan, or exploratory probe."""

    def __init__(
        self,
        planner: RulePlanner,
        goal_manager: GoalManager,
        probe_planner: ProbePlanner,
        logical_rulebook: Rulebook,
        memory: EngineMemory,
        event_sink=None,
    ) -> None:
        self.planner = planner
        self.goal_manager = goal_manager
        self.probe_planner = probe_planner
        self.logical_rulebook = logical_rulebook
        self.memory = memory
        self.event_sink = event_sink
        self.active_plan: ActivePlan | None = None
        self.last_decision: PlanDecision | None = None

    def choose_action(
        self,
        state: EngineState,
        task_goal: Goal,
        actions: list[GameAction],
        legend: dict[int, str] | None = None,
    ) -> PlanDecision:
        decision = self._continue_active_plan(state)
        if decision is None:
            rule_plan = self.planner.plan_to_goal(state, task_goal, actions)
            if rule_plan:
                self.active_plan = ActivePlan(
                    goal=task_goal,
                    actions=tuple(rule_plan),
                    index=1,
                    exploratory=False,
                )
                action = rule_plan[0]
                decision = PlanDecision(
                    action=action,
                    reason="rule_plan",
                    plan=rule_plan,
                    predictions=tuple(self.logical_rulebook.predict(state, action)),
                    remaining_actions=tuple(rule_plan[1:]),
                )
            else:
                subgoal = self._choose_subgoal(
                    state, task_goal, actions, legend
                )
                probe_plan = self._create_probe_plan(
                    state, subgoal, actions, legend
                )
                self.active_plan = ActivePlan(
                    goal=subgoal,
                    actions=tuple(probe_plan),
                    index=1,
                    exploratory=True,
                )
                action = probe_plan[0]
                decision = PlanDecision(
                    action=action,
                    reason="explore_subgoal",
                    plan=probe_plan,
                    subgoal=subgoal.description,
                    exploratory=True,
                    predictions=tuple(self.logical_rulebook.predict(state, action)),
                    remaining_actions=tuple(probe_plan[1:]),
                )
        self.last_decision = decision
        return decision

    def _choose_subgoal(
        self,
        state: EngineState,
        task_goal: Goal,
        actions: list[GameAction],
        legend: dict[int, str] | None,
    ) -> Goal:
        try:
            return self.goal_manager.choose_subgoal(
                current=state,
                task_goal=task_goal,
                actions=actions,
                memory=self.memory,
                logical_rulebook=self.logical_rulebook,
                legend=legend,
            )
        except ValueError as exc:
            if "provider error" in str(exc).lower():
                raise
            self._log_fallback("subgoal", exc)
            subgoal = Goal(
                "try one available action and observe the result",
                kind="subgoal",
            )
            self.goal_manager.set_subgoal(subgoal)
            return subgoal

    def _create_probe_plan(
        self,
        state: EngineState,
        subgoal: Goal,
        actions: list[GameAction],
        legend: dict[int, str] | None,
    ) -> list[GameAction]:
        try:
            plan = self.probe_planner.create_plan(
                state=state,
                subgoal=subgoal,
                actions=actions,
                memory=self.memory,
                logical_rulebook=self.logical_rulebook,
                legend=legend,
            )
            if not plan:
                raise ValueError("LLM returned an empty action plan")
            return plan
        except ValueError as exc:
            if "provider error" in str(exc).lower():
                raise
            self._log_fallback("action plan", exc)
            if not actions:
                raise ValueError("No available action for fallback plan") from exc
            return [actions[0]]

    def _log_fallback(self, stage: str, exc: ValueError) -> None:
        message = f"Malformed {stage} response; using one-action fallback: {exc}"
        if self.event_sink is not None:
            self.event_sink(message)
        else:
            print(message)

    def invalidate_active_plan(self) -> None:
        self.active_plan = None

    def _continue_active_plan(self, state: EngineState) -> PlanDecision | None:
        if self.active_plan is None:
            return None
        action = self.active_plan.next_action()
        if action is None:
            self.active_plan = None
            return None
        current_plan = self.active_plan
        self.active_plan = current_plan.advance()
        return PlanDecision(
            action=action,
            reason="active_plan",
            plan=list(current_plan.actions[current_plan.index :]),
            subgoal=current_plan.goal.description,
            exploratory=current_plan.exploratory,
            predictions=tuple(self.logical_rulebook.predict(state, action)),
            remaining_actions=tuple(
                current_plan.actions[current_plan.index + 1 :]
            ),
        )
