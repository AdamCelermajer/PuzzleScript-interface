---
date: 2026-10-22
title: ACDL specs and renders of the four frameworks
threads: [harness-revamp, harness2, avo-campaigns]
runs: []
commits: []
docs: [docs/architecture/acdl/overview.png, docs/architecture/acdl/overview.acdl, docs/architecture/acdl/baseline-controller.acdl, docs/architecture/acdl/baseline-agent.acdl, docs/architecture/acdl/harness2.acdl, docs/architecture/acdl/avo.acdl]
reconstructed: false
brief: true
---
## Did
- Wrote each framework's prompt structure in ACDL (CAIS 2026) and rendered it with the official visualizer at acdlang.org: baseline controller-driven, baseline agent-driven, Harness² (player and coach) and AVO (optimizer and player).
- Added each framework's tools with a one-line description: `act.py` for the controller, `game.py look / do / reset` for the agent driver, the skill and task tools for Harness², and the AVO optimizer and player interfaces.
- Drew a simplified overview in which the coding agent (OpenCode, Codex, Claude Code) is one loop of tool calls and results per instruction.
## Found
- All four frameworks share one core: an instruction, then tool calls until the agent replies. They differ in who sends the instruction and what it contains.
## Decided
- Use only the official visualizer, no custom renderer.
## Next
- —
