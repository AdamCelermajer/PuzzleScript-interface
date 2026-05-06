# Learning Loop Pseudocode

## Responsibility

Coordinate the environment, perception, transition history, reasoning, subgoal planning, action selection, and persistence.

## Pseudocode

```python
def run_learning_agent(game_id, backend_url, max_steps):
    environment = EnvironmentSurface.open(game_id, backend_url)
    persistent_store = PersistentKnowledgeStore()
    active_context = ActiveTaskContext(game_id)
    transition_history = TransitionHistory(max_size=200)

    active_context.load_relevant_prior_knowledge(persistent_store)

    observation = environment.reset()
    perceived_state = perceive(observation, active_context, persistent_store)

    for step in range(max_steps):
        should_reason = should_refine_beliefs(
            transition_history=transition_history,
            active_context=active_context,
            perceived_state=perceived_state,
        )

        if should_reason:
            evidence = transition_history.evidence_for_reasoning(active_context)
            reasoning_update = reason_about_transitions(
                evidence=evidence,
                active_context=active_context,
                persistent_store=persistent_store,
            )
            active_context.apply_reasoning_update(reasoning_update)
            persistent_store.save_reasoning_update(game_id, reasoning_update)

        subgoal_update = plan_subgoal(
            active_context=active_context,
            transition_history=transition_history,
            perceived_state=perceived_state,
        )
        active_context.apply_subgoal_update(subgoal_update)

        previous_state = perceived_state
        action, next_observation = act(
            environment=environment,
            perceived_state=perceived_state,
            active_context=active_context,
        )

        perceived_state = perceive(next_observation, active_context, persistent_store)
        transition = transition_history.record(
            previous_state=previous_state,
            action=action,
            next_state=perceived_state,
            outcome=next_observation.state,
        )

        persistent_store.save_subgoal_update(
            game_id=game_id,
            subgoal_update=subgoal_update,
            outcome=evaluate_subgoal_outcome(subgoal_update, transition),
        )

        if perceived_state.status in {"WIN", "GAME_OVER"}:
            break
```

## Notes

The target loop is evidence-triggered. The current implementation may still use fixed step intervals for some analysis, but this pseudocode keeps that policy replaceable.
