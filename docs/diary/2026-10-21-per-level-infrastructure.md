---
date: 2026-10-21
title: Levels as tasks: start at level k, end at its win, per-level score
threads: [harness2, codex-direct-player, avo-campaigns, arc-environment, workbench]
runs: []
commits: []
docs: [docs/research/per-level-interface.md, docs/research/harness2-per-level-feasibility.md]
reconstructed: false
brief: true
---
## Did
- Runtime `/init` and ARC `RESET` take `level` (1-based, playable levels only; message screens skipped); a bad level or level index is a 400, not a 500. `ArcadeEnv(start_level=k)` sends it on the first reset and refuses a service that ignores it.
- Baseline (both drivers): `--start-level`, `stop_after_levels` counted from it, launch options `start_level` / `one_level`; `result.json` gets `levels` and `level_solved/moves/shortest/ratio` (`frameworks/levels.py`).
- AVO: `continue_levels` option, where each research session starts where the previous one stopped and solvers still play from level 1.
- Workbench: "game · level k" on the run list, run page and Compare (level filter); Results matrix rows per one-level task.
- Second game-service instance from the current code on 3212/8002 (not 8001, the Enqueue backend's port); the shared 3210/8000 serve live runs and run old code.
## Found
- Shortest solutions (BFS, semantic mode): Modality 6/33/66/158 (matches `modality.py`), IceCrates 4/5/12/29/8/32, Knightoban 20/10/–/41/–/28 (levels 3 and 5 hit the 10-min search limit).
## Decided
- Adam: the player sees its level and the total; the per-level budget is just `max_steps`; shortest solutions are metadata, absent when unknown; AVO stays whole-game by default.
## Next
- Harness² level loop (other session) adds `--stop-after-levels 1` and uses port 8002.
