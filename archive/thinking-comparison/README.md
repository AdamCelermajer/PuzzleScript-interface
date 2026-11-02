# LLM Thinking Comparison - `ps_sokoban_basic-v1`

Run date: 2026-06-22
Game: `ps_sokoban_basic-v1`
Backend: local PuzzleScript stack (`http://localhost:8000`)

This folder keeps the first comparison run only. The failed uncapped Kimi retry
was removed because it crashed before producing a useful comparable decision.

## Kept Conditions

| Folder | Model | Thinking mode | Thinking recorded? | Steps completed | Final state |
|---|---|---:|---:|---:|---|
| `deepseek-thinking/` | `deepseek/deepseek-v4-pro` | On | Yes | 5 / 5 | Max steps reached |
| `kimi-thinking/` | `moonshotai/kimi-k2.6` | On | Yes | 1 / 5 | Crashed on second move-selection call |
| `kimi-no-thinking/` | `moonshotai/kimi-k2.6` | Off | No | 5 / 5 | Max steps reached |

## Initial State Check

All three kept conditions started from the same Sokoban state.

```text
grid hash:  bdadc2528690c0d2
image hash: f098c9a32242989f
game_id:    ps_sokoban_basic-v1
state:      PLAYING
progress:   0 / 2 levels completed
actions:    ACTION1, ACTION2, ACTION3, ACTION4, ACTION5, ACTION7
```

Initial grid:

```text
1 1 1 1 0 0
1 0 5 1 0 0
1 0 0 1 1 1
1 4 2 0 0 1
1 0 0 3 0 1
1 0 0 1 1 1
1 1 1 1 0 0
```

## First Decisions

| Condition | First action | First subgoal |
|---|---|---|
| `deepseek-thinking` | `ACTION3` | Move player to the right side of the box at `(4,3)` to prepare for pushing it left toward the target |
| `kimi-thinking` | `ACTION1` | Move the player to the cell directly below the top box |
| `kimi-no-thinking` | `ACTION1` | Identify which action controls movement in which direction |

## Recorded Thinking Files

- `deepseek-thinking/thinking_20260622T121610.json` - 11,573 chars of reasoning.
- `kimi-thinking/thinking_20260622T124354.json` - 51,075 chars of reasoning.

Both files contain:

- `timestamp`
- `model`
- `purpose` (`subgoal/action`)
- `reasoning`
- `final_output`
- `response_time_seconds`

## Action Sequences

### `deepseek-thinking`

1. `ACTION3` - move player to right side of box to push it left toward target.
2. `ACTION1` - learn effect of `ACTION1`.
3. `ACTION2` - push box right to align with target.
4. `ACTION1` - verify `ACTION1` moves player up.
5. `ACTION3` - push box left to free path.

### `kimi-thinking`

1. `ACTION1` - move player directly below the top box.
2. Crashed on the next move-selection call with `LLM returned empty content`.

### `kimi-no-thinking`

1. `ACTION1` - identify movement directions.
2. `ACTION3` - interact with the box.
3. `ACTION2` - determine what `ACTION2` does.
4. `ACTION2` - observe effect on player position.
5. `ACTION1` - observe effect on pushing box downward.

## Observations

1. Kimi's first thinking trace is much larger than DeepSeek's and produced much
   higher latency.
2. Kimi without thinking was far faster and completed the 5-step run.
3. Kimi with thinking produced a useful first decision artifact but did not
   complete the run.
4. DeepSeek with thinking completed the 5-step run, but response times were
   highly variable.
5. The reasoning traces show both models spending substantial effort inferring
   tile meanings and action semantics.

## Artifact Layout

Each condition folder contains:

- `timeline.jsonl` - state/action/state transitions observed.
- `rules.json` - logical rules proposed or accepted during the run.
- `log.txt` - console log with call latencies and decisions.
- `thinking_*.json` - recorded reasoning, when thinking was enabled and captured.

## Caveats

- Only the first `subgoal/action` call was recorded per thinking condition.
- `kimi-thinking` is comparable only for the first decision because it crashed
  before completing the second move-selection call.
- The code changes used to capture thinking were experimental and are not kept
  in the production client.
