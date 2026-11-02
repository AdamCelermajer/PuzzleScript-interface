---
date: 2026-07-16
title: Agent workbench and verified rule learning
threads: [workbench, rule-agent]
runs: []
commits: [9d9c505]
docs: [docs/notes/workbench-notes.md, docs/pseudocode/manifest.json]
reconstructed: true
brief: true
---
## Did
- Added the agent workbench (FastAPI backend under `workbench/`, website pages) with live play, replay and editable pseudocode.
- Landed verified rule learning in `client/engine/` (natural rule → logical rule → verification → use), with tests.
- Ran four short smoke runs on Sokoban through the Codex provider (`gpt-5.6-sol`, low effort, 2–50 step caps).
## Found
- —
## Decided
- Demo flow for meetings: workbench controls, replay of the promising Sokoban run, one rule-learning attempt, pseudocode view (`docs/notes/workbench-notes.md`).
## Next
- Add simple agent baselines and reference solutions.
