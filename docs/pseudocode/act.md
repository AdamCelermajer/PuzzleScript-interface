# Act Pseudocode

## Responsibility

Select and execute the next action using the active context and current subgoal.

## Inputs

- perceived state
- active task context
- current subgoal
- available actions

## Outputs

- selected action
- next environment observation

## Pseudocode

```python
def choose_action(perceived_state, active_context):
    candidate_actions = perceived_state.available_actions

    scored_actions = []
    for action in candidate_actions:
        predicted_effect = predict_effect(
            action=action,
            state=perceived_state,
            rules=active_context.known_rules,
            hypotheses=active_context.hypotheses,
        )

        score = score_action(
            action=action,
            predicted_effect=predicted_effect,
            subgoal=active_context.current_subgoal,
            final_goal=active_context.final_goal,
        )
        scored_actions.append((score, action))

    return highest_scoring_action(scored_actions)


def act(environment, perceived_state, active_context):
    action = choose_action(perceived_state, active_context)
    next_observation = environment.step(action)
    return action, next_observation
```

## Notes

The current implementation may select actions directly through an LLM prompt. The target design can replace or augment that with search, heuristics, or learned transition prediction.
