---
date: 2026-05-12
title: Goal-recognition evaluation, design and first runners
threads: [goal-recognition]
runs: []
commits: [c89e7ff, 9d7d41a, aee918f, bdcf163, 10cfab3, d41593f, 9d94c42, 963bc86, c3dc905, d648111, 7cf7df8, 3daecf3, 972efe7, cba9545, d3147d4]
docs: [studies/goal_recognition/docs/2026-05-12-goal-recognition-evaluation-design.md, studies/goal_recognition/docs/2026-05-12-goal-recognition-evaluation.md]
reconstructed: true
---
## Did
- Designed and planned an evaluation of whether a model can state a game's goal from its frames.
- Built one-frame, ten-frame and "visible" goal-recognition runners plus review and report tools.
- Switched the LLM config to DeepSeek V4 Pro; the random runner and goal review now skip the unsupported ACTION6.
- May 13: review tools accept BOM-prefixed JSONL and force a colour board.
## Found
- —
## Decided
- Treat goal recognition as a separate side study from rule learning.
## Next
- Curate a game pool and run a model matrix.
