---
date: 2026-07-26
title: Codex direct-player baseline, BFS reference solutions, benchmark positioning
threads: [benchmark-curation, codex-direct-player]
runs: []
commits: [29c4205, 4928482]
docs: [docs/notes/benchmark-positioning.md, docs/notes/todo.md, experiement/bfs_solver/REPORT.md]
reconstructed: true
---
## Did
- Added `studies/codex_agent/`: one persistent Codex SDK session that receives frames and returns one action per turn, with no experiment-owned tools.
- Built an exact BFS solver over the PuzzleScript engine and ran it on a 30-game sample (first level, 100k states or 10 s).
- Persisted replay plan history; added a whole-game optimal path view.
- Wrote the benchmark positioning note and a todo list (agent correctness, prompting, paper decisions).
## Found
- 137 of 193 games are deterministic with formal win conditions; BFS solved 13/30 sampled first levels, all replay-verified (`experiement/bfs_solver/REPORT.md`).
- Correct BFS runs at about 185 new edges/s because each edge replays its prefix; scalable search needs engine clone/restore.
## Decided
- Score a successful run as `optimal_actions / agent_actions`, counting every environment action (`benchmark-positioning.md`).
- Claim: controlled capability decomposition, not just a new game collection.
## Next
- Contamination controls, a deterministic benchmark subset, more baselines.
