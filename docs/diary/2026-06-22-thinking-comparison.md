---
date: 2026-06-22
title: Thinking vs no-thinking comparison on Sokoban
threads: [rule-agent]
runs: []
commits: [3c97a7a, 792fb13]
docs: []
reconstructed: true
---
## Did
- Ran the rule agent on `ps_sokoban_basic-v1` from one shared start state (grid and image hashes checked) with a 5-step cap.
- Conditions: DeepSeek V4 Pro with thinking, Kimi K2.6 with and without thinking. Kept the artifacts in `thinking-comparison/`.
- Jun 23: refined the architecture pseudocode view.
## Found
- DeepSeek thinking and Kimi no-thinking completed 5/5 steps (step cap reached); Kimi thinking crashed on its second move-selection call (1/5). No level was solved within 5 steps (`thinking-comparison/README.md`).
## Decided
- Drop the uncapped Kimi retry; it crashed before producing a comparable decision.
## Next
- —
