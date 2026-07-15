# Engine Wiring

## Card Title

**File role** Build the reasoning modules

## Pseudocode

```text
base_path <- game_rules_path(cfg.rules_dir, cfg.game)
memory <- EngineMemory(base_path / "timeline.jsonl")
natural_rule_library <- NaturalRuleLibrary(base_path / "natural_rules.json")
logical_rulebook <- LogicalRulebook(base_path / "rules.json")
failure_log <- RuleFailureLog(base_path / "rule_failures.jsonl")
verifier <- RuleVerifier(memory)
natural_rule_inducer <- NaturalRuleInducer(llm)
logic_rule_compiler <- LogicRuleCompiler(llm)
rule_learner <- RuleLearner(
    natural_rule_inducer,
    natural_rule_library,
    logic_rule_compiler,
    logical_rulebook,
    verifier,
    failure_log,
    max_logic_attempts = 3,
    allowed_exhausted_hypotheses = 3
)
goal_manager <- GoalManager(llm)
planner <- RulePlanner(logical_rulebook)
probe_planner <- ProbePlanner(llm)
action_selector <- ActionSelector(planner, goal_manager, probe_planner, logical_rulebook, memory)
return EngineArchitecture(
    perceiver,
    memory,
    natural_rule_library,
    logical_rulebook,
    rule_learner,
    goal_manager,
    planner,
    probe_planner,
    action_selector
)
```
