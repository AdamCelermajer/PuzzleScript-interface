---
date: 2026-09-04
title: Direct-player baseline vs baseline+ on Sokoban
threads: [codex-direct-player]
runs: [output/codex_agent/gpt55-xhigh-baseline-plus*, output/codex_agent/luna-medium-baseline*]
commits: []
docs: [studies/codex_agent/README.md]
reconstructed: true
---
## Did
- Defined the direct-player conditions: `baseline` (one persistent session, one action per turn) and `baseline-plus` (same, plus `list_notes`/`read_note`/`write_note` and a required `strategy.md`).
- Ran GPT-5.5 and GPT-5.6 Luna on `ps_sokoban_basic-v1` (task goal: complete level 1); Sep 5 audit reruns at 100–150 steps.
## Found
- Luna high reached the goal in both arms (baseline 49 actions, baseline+ 58); GPT-5.5 medium baseline+ with fixed notes in 74; GPT-5.5 medium baseline ended 0/2 at 100 and at 200 steps.
- Sep 5: GPT-5.5 xhigh baseline+ 1/2 at 100 steps; Luna medium 0/2 at 150 in both arms.
- Several Sep 5 runs aborted on the isolation guard ("Unapproved model tool: exec / tool_search"); one on "Selected model is at capacity".
## Decided
- —
## Next
- Run harder games than Sokoban.
