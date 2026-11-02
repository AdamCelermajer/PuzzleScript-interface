---
date: 2026-08-24
title: First AVO runs on Sokoban
threads: [avo-campaigns]
runs: []
commits: []
docs: [docs/research/avo-framework.md, docs/architecture/avo-framework-acdl.png]
reconstructed: true
brief: true
---
## Did
- Aug 23: first AVO agent runs on `ps_sokoban_basic-v1`: three with `gpt-5.6-sol` (high) and five with `anthropic/claude-opus-5-fast` via OpenRouter (`avo/output/20260823T*`).
- Aug 24: full Sokoban runs `avo/output/sokoban-basic-full-20260824` and `-v04-`; general-agent smoke tests in `output/avo-general-smoke*`; lab demo folders.
## Found
- Both full Sokoban runs won (126 and 84 environment steps).
- The Aug 23 runs left no summary files; two Opus runs stopped after 0 and 1 model requests.
## Decided
- —
## Next
- Try a harder game (Midas) and an outer loop over complete agent runs.
