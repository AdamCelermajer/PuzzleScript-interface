# PuzzleScript BFS solver experiment

This is an isolated experiment for measuring whether the existing JavaScript
PuzzleScript engine is fast enough to serve as the transition simulator for an
oracle solver.

Everything in this experiment is contained in this directory. It does not
modify `puzzlescript_interface/runtime/`, the installed PuzzleScript package,
or any production API.

## Complete machine-state adapter

`machine_state_adapter.js` adds an experiment-local state-in/action-out layer
over the mutable npm engine:

```javascript
const adapter = new PuzzleScriptMachineAdapter({ source, levelIndex });
const initial = adapter.initialState;
const { state: next, won } = await adapter.transition(initial, action);
```

The adapter stores board contents, movement intent, pending input, `AGAIN`
state, ordered rule-cache membership, and ellipsis linkages. On import it
rebuilds a level and restores the captured dynamic cache state. Static parsed
rules and sprite definitions remain shared.

`machine_state_codec.js` compacts complete states into typed arrays for storage
in the BFS graph. `stateful_solver.js` stores one compact complete state plus a
parent index and incoming action per unique node; it never replays the action
prefix to expand a node.

The stateful solver has two visited-key modes:

- `exact` includes ordered internal cache history. It audits the literal npm
  engine, but can create thousands of variants of the same game position.
- `semantic` still stores and branches from a complete real engine state, but
  merges nodes with the same board, movement intent, level, pending input, and
  `AGAIN` state. This avoids derived-cache state explosion. Returned paths are
  always replay-verified; strict optimality over accidental cache-history
  variants is not claimed.

This adapter intentionally uses internal properties from PuzzleScript
`6.0.0-alpha.2`, including `_setLevel` and `_getSpriteByName`, because the
package's public snapshot API is incomplete. Compatibility tests fail loudly
if those internals disappear. If this prototype later moves into production,
the clean follow-up is to expose equivalent export/import operations as a
supported engine API.

Current exact-state support retains the experiment's deterministic,
turn-based, no-checkpoint eligibility restrictions. Random-number state,
realtime scheduling, full undo history, and mid-level checkpoints need extra
machine-state fields before those games can be included.

The batch runner selects a reproducible sample of 30 games and searches the
first playable level of each game using FIFO breadth-first search.

## Eligibility

A game is included when:

- `script.txt` parses with the installed `puzzlescript` package;
- the parsed game contains a non-empty formal `WINCONDITIONS` list;
- it has at least one map level;
- the source does not use random rules, realtime execution, or checkpoints.

This first experiment intentionally excludes rule-command-only goals and
features with clear non-board runtime state.

## State and loop filtering

The engine state is encoded as one `Uint16` cell-signature ID per board cell.
A signature is the sorted set of internal PuzzleScript sprite names together
with their movement intents, so overlapping objects and pending directions
remain visible to the solver. The complete byte array is used as the visited
key; visible ARC colors are not used.

Each frontier node stores only its compact board, parent index, and incoming
action. It does not store a JSON snapshot or full action path. This keeps BFS
memory proportional to roughly two bytes per cell plus map/key overhead.

The npm engine also maintains private ordered rule-match caches that are not
part of its snapshot API. Mutating one engine back to an old board produced a
false solution in an early run. To avoid that artifact, every candidate edge
is evaluated in a fresh engine by replaying its node's real action prefix and
then applying the candidate action. This is slower, but every discovered edge
is an actually replayable trajectory. The output reports candidate BFS edges
separately from all engine actions spent on prefix replay.

Search actions are `UP`, `DOWN`, `LEFT`, `RIGHT`, and the generic `ACTION`
button when the parsed game does not declare `noAction`. Game-specific labels
such as Slidings' `X` are aliases for that generic button; the ARC surface calls
it `ACTION5`. `UNDO` and `RESTART` are omitted because forward BFS already
retains predecessor states and the initial state.

## Why this is not bidirectional BFS

PuzzleScript provides a successor function, but not a generic predecessor
generator. Rules may create/delete objects, execute repeatedly, cancel a turn,
or map many predecessor states to one successor. Formal win conditions also
describe a set of boards rather than one concrete goal board.

The experiment therefore uses forward BFS with exact duplicate-state loop
filtering. Reverse edges or rule-regression landmarks can be added separately,
but are not labelled bidirectional search here.

## Run

```powershell
node experiement/bfs_solver/run_sample.js
```

Defaults:

- seed: `3838`
- sample size: `30`
- state limit: `100000` per game
- time limit: `10` seconds per game
- repeated `AGAIN` tick limit: `100` per action

Override them with, for example:

```powershell
node experiement/bfs_solver/run_sample.js --seed 3838 --sampleSize 30 --maxStates 100000 --timeoutMs 10000
```

Generated artifacts:

- `sample.json` - candidate scan, exclusions, and selected games
- `results.json` - complete machine-readable results
- `results.csv` - flat result table
- `REPORT.md` - readable summary and solved-game list
- `verification.json` - independent replay check of every reported solution

The batch runner executes the independent replay check automatically and
fails instead of publishing a report if any claimed solution does not replay.

Run the focused tests with:

```powershell
node --test experiement/bfs_solver/solver.test.js
```

Run the complete-state adapter, codec, and stateful-BFS differential tests:

```powershell
node --test experiement/bfs_solver/machine_state_adapter.test.js experiement/bfs_solver/stateful_solver.test.js
```

Run one game using complete-state BFS without prefix replay:

```powershell
node experiement/bfs_solver/stateful_solve_game.js --gamePath puzzlescript_interface/games/ps_sokoban_basic-v1/script.txt --gameId ps_sokoban_basic-v1 --levelIndex 0 --maxStates 100000 --timeoutMs 10000
```

Rerun the reproducible 30-game sample with complete-state BFS, separate output
artifacts, and mandatory replay verification:

```powershell
node experiement/bfs_solver/run_stateful_sample.js --timeoutMs 60000 --maxStates 100000 --visitedMode semantic --outputPrefix stateful_60s
```

To rerun only games that were unsolved in the original 10-second baseline:

```powershell
node experiement/bfs_solver/run_stateful_sample.js --timeoutMs 60000 --maxStates 100000 --onlyPreviousUnsolved true --outputPrefix stateful_unsolved_60s
```

Replay every solved path from a fresh engine instance with:

```powershell
node experiement/bfs_solver/verify_results.js
```

Rerun only the original 10-second timeouts with a 60-second limit:

```powershell
node experiement/bfs_solver/run_unsolved_60s.js
```
