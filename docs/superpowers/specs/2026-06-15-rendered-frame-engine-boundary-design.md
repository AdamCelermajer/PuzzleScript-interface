# Rendered Frame And Engine Boundary Design

Date: 2026-06-15

## Goal

Add a real rendered PuzzleScript image to each local observation while keeping
the client compatible with official ARC-AGI-3 challenges. At the same time,
clean up the client boundary so `client/engine/` is about reasoning, not
environment transport or UI.

## Principles

- ARC compatibility stays intact: `frame` remains the required machine-readable
  observation and `rendered_frame` is an optional extension.
- The engine receives one observation contract and returns an action decision.
- The engine may choose an action, but it must not execute that action against
  PuzzleScript, ARC, HTTP, or any other backend.
- Environment adapters, action execution, and dashboards live outside
  `client/engine/`.
- Local PuzzleScript should provide real PuzzleScript sprite rendering, not a
  recolored ARC grid.

## Target Flow

```text
PuzzleScript runtime
  -> frame + rendered_frame

PuzzleScript ARC adapter
  -> ARC-compatible frame fields + rendered_frame extension

client/arc adapter
  -> FrameData(rendered_frame=...)

client/runtime runner
  -> passes observation into engine
  -> executes returned action through the selected environment
  -> updates dashboard

client/engine
  -> observation in
  -> rule reasoning, memory, planning, action selection
  -> ActionDecision out
```

Official ARC responses do not need to include `rendered_frame`. The client must
default the field to `None` and continue using the grid-only path.

## Data Contract

`FrameData` remains the ARC-shaped client observation. Add an optional image
attachment:

```python
@dataclass(frozen=True)
class RenderedFrame:
    mime_type: str
    data_url: str


@dataclass
class FrameData:
    frame: list[list[list[int]]]
    ...
    rendered_frame: RenderedFrame | None = None
```

The local PuzzleScript extension should serialize as:

```json
{
  "rendered_frame": {
    "mime_type": "image/png",
    "data_url": "data:image/png;base64,..."
  }
}
```

This shape is intentionally generic enough for future JPEG/WebP output, but the
first implementation should emit PNG.

## Engine Boundary

The engine should consume an observation and return a decision:

```python
@dataclass(frozen=True)
class EngineObservation:
    frame_data: FrameData


@dataclass(frozen=True)
class ActionDecision:
    action: GameAction
    reason: str
    plan: list[GameAction]
    subgoal: str = ""
```

Allowed inside `client/engine/`:

- perception from `FrameData.frame` to `EngineState`
- transition memory and rulebook updates
- rule induction and LLM prompt construction
- action selection and action decision data

Not allowed inside `client/engine/`:

- `env.reset()`
- `env.step(...)`
- ARC toolkit calls
- PuzzleScript HTTP calls
- screen or terminal dashboard rendering

The engine can include `rendered_frame` in multimodal LLM prompt material when
present. If it is absent, the engine must use the current grid/text-only path.

## Proposed Package Layout

```text
client/
  arc/
    types.py
    arcade_env.py

  runtime/
    runner.py

  puzzlescript/
    screen_dashboard.py

  engine/
    observation.py
    perception.py
    memory.py
    rulebook.py
    induction.py
    planning.py
    actions.py
    reasoning.py
```

Compatibility shims can remain temporarily in old locations while entrypoints
and tests are migrated.

## PuzzleScript Rendering

The runtime should generate the image from real PuzzleScript rendering data:

- current level cells from the active `GameEngine`
- each cell's real `cell.getSprites()` stack
- `gameData.getSpriteSize()`
- each sprite's `sprite.getPixels(spriteHeight, spriteWidth)`
- PuzzleScript's existing sprite composition behavior, preferably through
  `BaseUI`-style pixel collapse logic

The first version should render the current board only. Message/title screen and
flickscreen/zoomscreen exact UI behavior can be handled later if needed.

## Dashboard

The new visual display is a client/runtime concern. It should show
`rendered_frame` on a screen-style dashboard and keep terminal rendering as a
fallback. The dashboard should not be imported by `client/engine/`.

Initial CLI behavior should use an explicit option such as:

```text
--dashboard terminal|screen
```

Terminal remains the default until the screen dashboard is stable.

## Testing

Focused tests should prove:

- PuzzleScript runtime responses include a valid PNG data URL for local games.
- The ARC adapter forwards `rendered_frame` without changing existing ARC fields.
- Official-ARC-style responses without `rendered_frame` still convert to
  `FrameData(rendered_frame=None)`.
- The engine accepts an observation with or without an image and still returns an
  action decision.
- The runtime runner, not the engine, calls `env.step(decision.action)`.

## Out Of Scope For First Pass

- Exact browser screenshot rendering.
- Full PuzzleScript title/message screen rendering.
- Replacing all compatibility imports in one large rewrite.
- Making image input mandatory for LLM calls.
- Changing the ARC integer frame projection.
