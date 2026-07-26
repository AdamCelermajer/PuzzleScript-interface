# Experiment-local machine-state transition API

## Outcome

The mutable PuzzleScript npm engine can be adapted to the desired interface
without changing the engine or runtime folders:

```text
transition(completeMachineState, action) -> nextMachineState
```

The implementation lives entirely in this experiment:

- `machine_state_adapter.js` captures, imports, and advances complete states.
- `machine_state_codec.js` stores those states compactly in typed arrays.
- `stateful_solver.js` runs FIFO BFS over complete states with exact duplicate
  filtering and shared parent pointers.
- `machine_state_adapter.test.js` differentially compares branches with fresh,
  uninterrupted engine executions.

## Why rule caches are included

`ps_compressed-v1` proved that reconstructing only the board and movement
flags is insufficient. Ordered rule-match cache membership can differ between
two histories and can change the npm engine's next transition. The adapter
therefore saves those cache memberships and restores them using cell indexes.

The tests cover branches from Sokoban, Compressed, Knightoban, Moving Target,
Wall Shuffle, and On and Off. They include the earlier false compressed path.

## Initial benchmarks

| Game | Result | Search throughput | Peak heap |
|---|---:|---:|---:|
| Sokoban Basic | optimal depth 33 | 7,457 edges/s | 82 MB |
| Wall Shuffle | optimal depth 11 | 789 edges/s | 59 MB |
| Compressed | 10-second timeout, no false goal | 836 edges/s | 170 MB |
| On and Off | 20-second timeout | 165 edges/s | 72 MB |

Sokoban's replay-safe implementation previously took about 1.3 seconds; the
complete-state implementation takes about 0.65 seconds and evaluates each BFS
edge directly. Performance varies heavily with rule complexity.

The compact On-and-Off initial state occupies about 2.9 KB. Before typed-array
compaction, ordinary JavaScript state objects caused roughly 654 MB of heap at
7,860 states. The compact representation used roughly 72 MB at 2,129 states in
the 20-second measurement.

## Remaining boundary

The adapter currently supports the deterministic experiment subset. Adding
random games, realtime games, checkpoints, or agent-facing undo requires
capturing their corresponding dynamic state too.

Complete-state branching removes prefix replay, but complex games still
produce many distinct states. Reaching solutions around depth 40 will likely
also require novelty-guided or goal-guided expansion rather than FIFO BFS
alone.
