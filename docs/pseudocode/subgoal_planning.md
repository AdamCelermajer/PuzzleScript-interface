# Subgoal Planning Pseudocode

## Responsibility

Choose the next useful subgoal or probe based on the current context and unexplained transitions.

## Inputs

- active task context
- transition history
- current perceived state

## Outputs

- selected subgoal
- action-plan hint
- failure signals

## Pseudocode

```python
def plan_subgoal(active_context, transition_history, perceived_state):
    rule_gaps = active_context.unresolved_questions()
    recent_actions = transition_history.recent_actions(limit=5)
    repeated_failures = detect_repeated_no_change(transition_history)

    if repeated_failures:
        target = choose_probe_that_changes_state(
            perceived_state=perceived_state,
            avoid_actions=recent_actions,
        )
    elif rule_gaps:
        target = choose_probe_for_rule_gap(
            rule_gaps=rule_gaps,
            perceived_state=perceived_state,
            known_rules=active_context.known_rules,
        )
    elif active_context.final_goal:
        target = choose_progress_subgoal(
            final_goal=active_context.final_goal,
            perceived_state=perceived_state,
            known_rules=active_context.known_rules,
        )
    else:
        target = choose_exploration_subgoal(
            perceived_state=perceived_state,
            recent_actions=recent_actions,
        )

    return SubgoalUpdate(
        selected_subgoal=target.description,
        action_plan_hint=target.plan_hint,
        failure_signals=repeated_failures,
    )
```

## Notes

Subgoal planning is not only for solving. It also drives experiments that reveal missing mechanics.
