# Transition History Pseudocode

## Responsibility

Store useful evidence as transitions: state before, action, state after, and outcome.

## Inputs

- `previous_state`
- `action`
- `next_state`
- `outcome`

## Outputs

- updated transition history
- selected evidence windows for reasoning

## Pseudocode

```python
class TransitionHistory:
    def __init__(max_size):
        self.transitions = []
        self.max_size = max_size

    def record(previous_state, action, next_state, outcome):
        transition = Transition(
            before=previous_state,
            action=action,
            after=next_state,
            outcome=outcome,
            changed=previous_state.frame != next_state.frame,
            novelty_score=estimate_novelty(previous_state, action, next_state),
        )

        self.transitions.append(transition)
        self.transitions = keep_recent_and_useful(self.transitions, self.max_size)
        return transition

    def evidence_for_reasoning(active_context):
        return select_transitions(
            transitions=self.transitions,
            prefer_changed=True,
            prefer_unknown_symbols=True,
            prefer_unexplained_effects=True,
            active_context=active_context,
        )

    def recent_actions(limit):
        return [transition.action for transition in self.transitions[-limit:]]
```

## Notes

The current implementation keeps a bounded history. The target architecture can keep a smarter evidence buffer rather than only a fixed recent window.
