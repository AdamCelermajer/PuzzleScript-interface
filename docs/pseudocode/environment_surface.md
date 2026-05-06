# Environment Surface Pseudocode

## Responsibility

Expose either PuzzleScript or ARC-AGI-3 through the same reset, observe, and step contract.

## Inputs

- `game_id`
- `backend_url`
- `action`

## Outputs

- `frame`
- `available_actions`
- `state`
- `reward_or_status`
- `levels_completed`

## Pseudocode

```python
class EnvironmentSurface:
    def open(game_id, backend_url):
        session = create_or_attach_session(game_id, backend_url)
        return session

    def reset(session):
        raw_response = backend.reset(session)
        return normalize_response(raw_response)

    def observe(session):
        raw_response = backend.observe(session)
        return normalize_response(raw_response)

    def step(session, action):
        raw_response = backend.step(session, action)
        return normalize_response(raw_response)

    def normalize_response(raw_response):
        return FrameData(
            frame=raw_response.frame,
            available_actions=raw_response.available_actions,
            state=raw_response.state,
            reward_or_status=derive_status(raw_response),
            levels_completed=raw_response.levels_completed,
        )
```

## Notes

The agent should not care whether the source is local PuzzleScript or official ARC-AGI-3. Differences belong behind this surface.
