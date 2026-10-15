---
date: 2026-04-12
title: ARC-compatible PuzzleScript service and the client / interface split
threads: [arc-environment]
runs: []
commits: [8cc5e38, 00e3855, e5f7334, a8cbc16, b4e8c98, 5012aa6, 1312ed5, 7c2db33, 9200d96, af53727, 73b5016, 2db05c5, 1d9e332, bc7e0ba, 192b428, de045b9]
docs: []
reconstructed: true
---
## Did
- Apr 10: added the PuzzleScript ARC-compatible service; moved the engine onto the ARC toolkit path; added ARC-based play and integration clients; documented the ARC-first workflow.
- Apr 12: split the repo into `client/` and `puzzlescript_interface/`; unified terminal views; restored the per-turn LLM learning loop; trimmed ARC boilerplate.
- Apr 13: moved games to `puzzlescript_interface/games/<name>/script.txt` with ARC-safe ids (`ps_<name>-v1`) and dropped the old solution files.
## Found
- —
## Decided
- The Python agent talks only to the ARC surface; the Node runtime stays internal.
## Next
- Return to the agent itself, starting from Sokoban.
