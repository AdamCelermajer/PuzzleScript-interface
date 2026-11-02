from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from client.engine.action_selector import ActionSelector, ProbePlanner
from client.engine.goal_manager import GoalManager
from client.engine.induction import (
    LogicRuleCompiler,
    NaturalRuleInducer,
    RuleLearner,
)
from client.engine.llm_client import Config
from client.engine.legend import LegendInferer, LegendStore
from client.engine.memory import EngineMemory
from client.engine.perception import Perception
from client.engine.prompts import PromptStore
from client.engine.natural_rules import NaturalRuleLibrary, RuleFailureLog
from client.engine.planner import RulePlanner
from client.engine.rulebook import Rulebook
from client.engine.rule_attempts import RuleAttemptLog
from client.engine.revision import RuleReviser
from client.engine.verifier import RuleVerifier


def game_rules_path(rules_dir: str | Path, game_id: str) -> Path:
    safe_name = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in game_id
    )
    return Path(rules_dir) / safe_name


@dataclass
class EngineArchitecture:
    perceiver: Perception
    memory: EngineMemory
    natural_rule_library: NaturalRuleLibrary
    logical_rulebook: Rulebook
    rule_learner: RuleLearner
    goal_manager: GoalManager
    planner: RulePlanner
    probe_planner: ProbePlanner
    action_selector: ActionSelector
    failure_log: RuleFailureLog
    legend_store: LegendStore
    rule_attempt_log: RuleAttemptLog
    prompt_store: PromptStore
    base_path: Path

    @property
    def rulebook(self) -> Rulebook:
        return self.logical_rulebook

    @property
    def inducer(self) -> RuleLearner:
        return self.rule_learner

    @classmethod
    def from_config(
        cls, config: Config, llm_client, event_sink=None
    ) -> "EngineArchitecture":
        base_path = game_rules_path(config.rules_dir, config.game)
        memory = EngineMemory(base_path / "timeline.jsonl")
        natural_rule_library = NaturalRuleLibrary(base_path / "natural_rules.json")
        logical_rulebook = Rulebook(base_path)
        failure_log = RuleFailureLog(base_path / "rule_failures.jsonl")
        legend_store = LegendStore(base_path / "legend.json")
        rule_attempt_log = RuleAttemptLog(base_path / "rule_attempt.jsonl")
        prompt_store = PromptStore(config.prompt_dir)
        verifier = RuleVerifier(memory)
        natural_rule_inducer = NaturalRuleInducer(llm_client, prompt_store)
        logic_rule_compiler = LogicRuleCompiler(llm_client, prompt_store)
        rule_learner = RuleLearner(
            natural_rule_inducer,
            natural_rule_library,
            logic_rule_compiler,
            logical_rulebook,
            verifier,
            failure_log,
            rule_attempt_log,
            rule_reviser=RuleReviser(llm_client, prompt_store),
            max_logic_attempts=3,
            allowed_exhausted_hypotheses=3,
            event_sink=event_sink,
        )
        goal_manager = GoalManager(
            llm_client,
            provide_end_goal=config.provide_end_goal,
            end_goal=config.end_goal,
            prompt_store=prompt_store,
        )
        planner = RulePlanner(logical_rulebook)
        probe_planner = ProbePlanner(llm_client, prompt_store)
        action_selector = ActionSelector(
            planner,
            goal_manager,
            probe_planner,
            logical_rulebook,
            memory,
            event_sink=event_sink,
        )
        return cls(
            perceiver=Perception(
                LegendInferer(llm_client, prompt_store),
                legend_store,
                provide_legend=config.provide_legend,
            ),
            memory=memory,
            natural_rule_library=natural_rule_library,
            logical_rulebook=logical_rulebook,
            rule_learner=rule_learner,
            goal_manager=goal_manager,
            planner=planner,
            probe_planner=probe_planner,
            action_selector=action_selector,
            failure_log=failure_log,
            legend_store=legend_store,
            rule_attempt_log=rule_attempt_log,
            prompt_store=prompt_store,
            base_path=base_path,
        )
