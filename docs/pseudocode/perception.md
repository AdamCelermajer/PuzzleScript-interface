# Perception & Legend

## Card Title

**File role** Translate the first frame into agent-readable state and legend

## Pseudocode

```text
initial_perception(frame):
    state <- perceive_state(frame)
    legend <- legend_inferer.infer(state.grid, state.image) # value = description
    legend_store.save(legend)
    return state, legend

perceive_state(frame):
    grid <- last_numeric_grid(frame)
    image <- frame.rendered_image
    return EngineState(
        grid,
        frame.state,
        frame.levels_completed,
        frame.win_levels,
        frame.game_id,
        image,
        frame.available_actions
    )
```
