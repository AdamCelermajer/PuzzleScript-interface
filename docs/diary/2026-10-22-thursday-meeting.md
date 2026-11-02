---
date: 2026-10-22
title: Supervisor meeting on the premise change and rule-learning curves
threads: [meetings, qwen-harness]
runs: []
commits: []
docs: [docs/research/thursday-20261022.html]
reconstructed: false
brief: true
---
## Did
- Presented the revised premise and the hypotheses H1 to H6 to Gal Kaminka and Yoav Goldberg (`docs/research/thursday-20261022.html`).
## Found
- The supervisors liked the direction and the results.
## Decided
- Graphs of rule learning as a function of tokens and of steps (game actions and ordinary tool calls).
- A look at reasoning compaction and deleted reasoning.
- A constrained condition where OpenCode is told that each turn its whole context and reasoning are wiped (system prompt kept) but it has a tool to save what it needs.
## Next
- Rule-learning curves first, from the 21 Oct runs.
- Check whether past reasoning reaches the model in our OpenCode sessions.
- Design the wiped-context condition.
