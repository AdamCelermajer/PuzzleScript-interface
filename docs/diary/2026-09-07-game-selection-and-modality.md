---
date: 2026-09-07
title: 20-game selection and GPT-5.5 on Modality
threads: [benchmark-curation, codex-direct-player]
runs: []
commits: []
docs: [docs/proposal/figures/modality-level1.png, docs/proposal/figures/modality-level2.png]
reconstructed: true
brief: true
---
## Did
- Picked a 20-game set (5 easy, 10 medium, 5 hard) with engine verification (`output/game-selection-20`).
- Ran GPT-5.5 high baseline+ on `ps_modality-v1` with a 1,000-step budget (three attempts).
## Found
- Attempt r3 reached 3/4 levels in about 293 actions; it identified undo and crate pushing early (see `docs/research/qwen27b-modality-failure-analysis.md`). It has no final result file.
- Attempts r1 and r2 aborted on the isolation guard (`tool_search`, `update_plan`).
## Decided
- —
## Next
- Six-game AVO campaigns.
