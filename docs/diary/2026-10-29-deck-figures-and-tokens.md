---
date: 2026-10-29
title: Diary deck redesign, period figures and tokens per run
threads: [workbench]
runs: []
commits: []
docs: [docs/research/diary-figures-20261029/avo-era/README.md, docs/research/diary-figures-20261029/qwen-era/README.md]
reconstructed: false
brief: true
---
## Did
- Present mode redesigned: cream deck with a warm dark variant (T), side outline (O), month progress bar, edge arrows, slides scaled to fit the screen, figures open full size on click, one slide per extra figure.
- New optional `brief: true` field: 17 minor entries fold into one "Also in <month>" slide per month.
- Every linked run now carries its token usage (`workbench/run_tokens.py`); slides show runs, tokens used, tokens generated and tokens by model. A continued run counts only its own new tokens.
- Eleven new figures with scripts and data under `docs/research/diary-figures-20261029/`: Midas, the six-game and DeepSeek AVO campaigns, Sep 14 world-model modes, direct-player baselines, period tokens (Aug to Sep); quantization, Qwen family on Modality, the vast 3×3, same-game coaching, the tool-call probe, tokens per move (Sep 30 to Oct 21).
## Found
- 160 of 262 linked runs have recorded usage; most of the rest used compact Codex tracing or predate usage logging. Linked runs total 2.36B tokens, 32M of them generated.
- Aug to Sep: 1.48B tokens over 72 runs, 95.5% cache hits.
- The three Sep 4 Sokoban runs recorded as 1/2 levels won both levels: before `c6a701a` the runtime did not count the final level of a won game (`avo-era/README.md`).
## Decided
- Slides lead with Found and figures; Did is folded on screen and shown in print.
## Next
- —
