# Per-level interface (Part 1 → Part 2)

22 Oct 2026. **Status: Part 1 is done and its tests pass** (all Python, Node and frontend suites; the only failure is `test_harness2_launch_flags_spec_and_entry`, which predates Part 2's new options). What the per-level infrastructure exposes, for the Harness² level loop (`frameworks/harness2/`, built in another session). Background: `harness2-per-level-feasibility.md`.

## Game services: use the second instance

Start-at-level-k needs the current `server.js` and ARC service. The shared services on **3210 (Node) and 8000 (ARC)** run older code and serve live runs: **never restart, replace or kill them**. A second instance from the current code runs on:

| Service | Port | URL for the launcher |
|---|---|---|
| Node runtime | 3212 | (internal) |
| ARC service | **8002** | `--backend-url http://localhost:8002`; containers reach it as **`http://host.docker.internal:8002`** (the launcher rewrites localhost) |

Not 8001: that port belongs to the dedicated Enqueue backend (`scripts/start-enqueue-backend.ps1`, `workbench/runs.py` `ENQUEUE_PORT`), and the workbench routes Enqueue launches there. It ran on 3211/8001 for an hour on 21 Oct and moved to 3212/8002 before any run used it.

**Not running since 22 Oct ~01:50**: it was started from an assistant session, whose background processes stop after 2 hours. Start it in two terminals that stay open, from the repository root:

```bash
PORT=3212 node puzzlescript_interface/runtime/server.js
ARC_PROXY_PORT=8002 PUZZLESCRIPT_SERVER_URL=http://127.0.0.1:3212 uv run python -m puzzlescript_interface.api.main
```

(PowerShell: `$env:PORT=3212; node puzzlescript_interface/runtime/server.js` and `$env:ARC_PROXY_PORT=8002; $env:PUZZLESCRIPT_SERVER_URL='http://127.0.0.1:3212'; uv run python -m puzzlescript_interface.api.main`.) Both write the same `puzzlescript_interface/.runtime/game_history.jsonl` debug log as the shared runtime.

Asking an old service (8000) for a start level fails with a clear `RuntimeError` ("this game service predates start levels") instead of silently playing level 1.

## Player flags (`python -m frameworks.baseline.agent`)

| Flag | Meaning |
|---|---|
| `--start-level k` | Open the game at playable level k (1-based; message screens are not counted). Reset and undo stay on level k. Default 1. |
| `--stop-after-levels N` | End the game once N levels are completed, **counted from the start level**. The next level is never shown. |
| `--max-steps B` | The action budget (the per-level budget is just this; you choose it). |

**The one-level task is `--start-level k --stop-after-levels 1 --max-steps B`.** `--start-level k` alone plays on from level k through the rest of the game. Part 2 passes all three.

The player sees its level and the total: the first instruction says "The game starts at level k of N." (only when k > 1), and `game.py look` shows `levels=k-1/N`. The end-of-run `solver.py` prompt asks for a solver "from level k".

The turn-based Baseline (`frameworks.baseline.run`) takes the same `--start-level` and `--stop-after-levels`.

Bad level: `--start-level 9` on a 4-level game exits with `error: <game>: level must be between 1 and 4, not 9.` and writes no `result.json` (the ARC service answers HTTP 400).

## Score fields in `result.json`

Both Baseline drivers add, from `transitions.jsonl`:

| Field | Meaning |
|---|---|
| `start_level` | k |
| `levels` | one entry per level played: `{level, solved, moves, shortest, ratio}` |
| `level_solved` | the start level was won (the one-level task's score) |
| `level_moves` | actions spent on the start level (resets and undos count) |
| `level_shortest` | fewest moves for that level, or `null` when unknown |
| `level_ratio` | `level_moves / level_shortest` when solved and known, else `null` (always ≥ 1) |

`levels_completed` and `win_levels` stay absolute (a solved level-3 task ends with `levels_completed = 3`). `reason` is `level_target_reached` when the level was won.

## Shortest solutions

`frameworks/levels.py`:

- `shortest(game_id, level) -> int | None`: fewest moves for one level (1-based), `None` when unknown.
- `SHORTEST[game_id]`: the tuple for levels 1, 2, ... (`shortest_solutions(game_id)` in `harness2/run.py` can be `list(levels.SHORTEST.get(game_id, ()))`).
- `stop_target(start_level, stop_after_levels)`, `level_scores(records, game_id, start_level, stop_after_levels)`, `result_fields(transitions_path, ...)`.

| Game | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|
| ps_modality-v1 | 6 | 33 | 66 | 158 | | |
| ps_icecrates-v1 | 4 | 5 | 12 | 29 | 8 | 32 |
| ps_knightoban-v1 | 20 | 10 | — (search hit its limit) | 41 | — (search hit its limit) | 28 |

Breadth-first search over the real engine (`experiement/bfs_solver/stateful_solver.js`, semantic mode, 3M states / 10 min per level); Modality matches `studies/thursday/modality.py`.

## Launch options (Baseline)

`start_level` (int, default 1), `one_level` (bool: stop after the start level), `stop_after_levels` (now counted from the start level). Variant labels: `Baseline · agent · level 3`, `· from level 3`, `· levels 2-3`.

## AVO: `continue_levels`

AVO still starts at level 1 and is scored over the whole game. With the option `continue_levels` (evolve flag `--continue-levels`), each research session starts at the level where the previous one stopped (its farthest level + 1, never earlier than its own start; kept in `campaign/level_progress.json` so a resume keeps it). Research score: fitness is the farthest level reached (absolute). Solver score: the fresh solver run and the self-checks still play from level 1. Each evaluation's score records `research_start_level`. Needs the second game-service instance.

## Workbench

- Catalog rows (direct play) carry `start_level`, `level` (set for a one-level task, including older runs that stopped after 1 level) and `level_score` (`{solved, moves, shortest, ratio}` from `result.json`).
- Run list, run page and Compare show "game · level k"; Compare's picker filters by level ("Level k only", "Whole game") to line up the same level across frameworks.
- The Results matrix gives each one-level task its own row, `game#Lk`, whose cell counts 1 when the level was solved.
- A Harness² per-level run with `levels/Lk/` is not yet read by the catalog; that is Part 2's view work.
