# Active Task Context Pseudocode

## Responsibility

Hold the current working beliefs for one environment run.

## State

- known environment rules
- inferred symbol legend
- current hypotheses
- current final goal
- current subgoal
- recent failure signals

## Pseudocode

```python
class ActiveTaskContext:
    def __init__(game_id):
        self.game_id = game_id
        self.known_rules = RuleSet()
        self.inferred_legend = {}
        self.hypotheses = []
        self.final_goal = None
        self.current_subgoal = None
        self.failure_signals = []

    def load_relevant_prior_knowledge(persistent_store):
        prior = persistent_store.retrieve(game_id=self.game_id)
        self.known_rules.merge(prior.rules)
        self.inferred_legend.update(prior.symbol_roles)
        self.hypotheses.extend(prior.reusable_hypotheses)
        self.final_goal = prior.goal_hint or self.final_goal

    def apply_reasoning_update(update):
        self.inferred_legend.update(update.legend_updates)
        self.known_rules.add_candidates(update.candidate_rules)
        self.known_rules.promote_validated(update.validated_rules)
        self.hypotheses = update.remaining_hypotheses
        self.final_goal = update.final_goal or self.final_goal

    def apply_subgoal_update(subgoal_update):
        self.current_subgoal = subgoal_update.selected_subgoal
        self.failure_signals.extend(subgoal_update.failure_signals)

    def unresolved_questions():
        return find_rule_gaps(
            known_rules=self.known_rules,
            hypotheses=self.hypotheses,
            failure_signals=self.failure_signals,
        )
```

## Notes

This is separate from persistent memory. It is the agent's current working state for the active environment.
