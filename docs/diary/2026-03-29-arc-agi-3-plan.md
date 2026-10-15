---
date: 2026-03-29
title: Rule-learning agent framework and the ARC-AGI-3 adaptation plan
threads: [rule-agent, arc-environment]
runs: []
commits: [b5a0a29, 522d264]
docs: [docs/research/context.acdl, docs/research/main_loop.acdl]
reconstructed: true
---
## Did
- Rewrote the agent as an LLM rule-learning framework (`learning_mode.py`, `prompts.py`, `env_adapter.py`).
- Added an engine and environment framework covering both PuzzleScript and ARC-AGI-3 tasks.
- Wrote `research_and_plan.md`: how ARC-AGI-3 agents talk to environments (`arc-agi` SDK, `GameAction` enum, scorecards) and a plan to match that protocol.
- Added prompt/orchestration sketches (`context.acdl`, `main_loop.acdl`) and NotebookLM source notes.
## Found
- —
## Decided
- Make PuzzleScript speak the ARC-AGI-3 protocol so one agent runs on both.
## Next
- Build the ARC-compatible service in front of the Node runtime.
