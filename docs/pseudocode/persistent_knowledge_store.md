# Persistent Knowledge Store Pseudocode

## Responsibility

Store reusable knowledge across runs and expose relevant prior knowledge to the active task context.

## Stored Knowledge

- validated rules
- compressed abstractions
- symbol-role priors
- goal templates
- useful subgoals and probes
- solved patterns

## Pseudocode

```python
class PersistentKnowledgeStore:
    def retrieve(game_id):
        return PriorKnowledge(
            rules=load_validated_rules(game_id),
            abstractions=load_reusable_abstractions(game_id),
            symbol_roles=load_symbol_role_priors(game_id),
            goal_hint=load_goal_hint(game_id),
            reusable_hypotheses=load_hypotheses(game_id),
        )

    def retrieve_rules(game_id):
        prior = self.retrieve(game_id)
        return prior.rules

    def save_reasoning_update(game_id, reasoning_update):
        save_validated_rules(game_id, reasoning_update.validated_rules)
        save_abstractions(game_id, reasoning_update.compressed_abstractions)
        save_symbol_roles(game_id, reasoning_update.legend_updates)

    def save_subgoal_update(game_id, subgoal_update, outcome):
        if outcome.was_useful:
            save_goal_pattern(game_id, subgoal_update.selected_subgoal)
            save_probe_strategy(game_id, subgoal_update.action_plan_hint)
```

## Notes

This is broader than the current rules file. The current implementation persists inferred rules, while the target store also preserves abstractions, goal patterns, and useful probes.
