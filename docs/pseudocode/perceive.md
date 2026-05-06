# Perceive Pseudocode

## Responsibility

Turn an environment observation into the agent's working representation.

## Inputs

- `raw_frame_data`
- `active_context`
- `persistent_knowledge`

## Outputs

- `perceived_state`
- optional `new_symbols`
- optional `changed_features`

## Pseudocode

```python
def perceive(raw_frame_data, active_context, persistent_knowledge):
    frame = raw_frame_data.frame
    available_actions = raw_frame_data.available_actions
    status = raw_frame_data.state

    symbols = extract_symbols(frame)
    unknown_symbols = symbols - active_context.known_symbols

    prior_symbol_roles = persistent_knowledge.lookup_symbol_priors(
        game_id=raw_frame_data.game_id,
        symbols=symbols,
    )

    perceived_state = PerceivedState(
        frame=frame,
        available_actions=available_actions,
        status=status,
        symbols=symbols,
        unknown_symbols=unknown_symbols,
        prior_symbol_roles=prior_symbol_roles,
    )

    return perceived_state
```

## Notes

Perception should be conservative. It may attach hypotheses, but it should not silently promote guesses into known rules.
