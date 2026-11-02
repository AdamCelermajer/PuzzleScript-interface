---
date: 2026-09-14
title: Workflow consolidation, Docker isolation and Astra/Luna six pairs
threads: [avo-campaigns, workbench, benchmark-curation]
runs: []
commits: [c6a701a]
docs: [docs/research/diary-figures-20261029/avo-era/fig3_sep14_world_model_modes.png, docs/architecture/workbench.md, docs/architecture/avo-framework.acdl, benchmark/vetting/README.md, docs/research/diary-figures-20261029/avo-era/README.md]
reconstructed: true
brief: true
---
## Did
- Committed `c6a701a`: AVO Docker isolation (`avo/docker/`, request guard and capture proxy), OpenRouter model provider, the `workbench/` backend (catalog, bounded batch jobs, comparisons, submissions) and the runs pages.
- Benchmark vetting: catalog audit, runtime smoke and `selection-v0.json` (30 games).
- Retired the OpenCode launcher; old OpenCode logs stay readable.
- Ran six games × {final-only, between-hypotheses} world-model modes (Astra medium outer, Luna medium inner), plus recoveries.
## Found
- Solved in both modes: feeling_like_filling 6/6, mowing 4/4, fatigued_square_maze 8/8; after storage recovery 2d_whale_world 8/8.
- The first batch lost three games to "No space left on device"; a Luna xhigh rerun hit a Codex usage limit; its recovery solved compressed 4/4 (both modes) and using_pushers 4/4 (final-only) / 3/4 (between-hypotheses).
- Audit of 66 candidates: the main repeated failure is turning evidence and strategy into a correct executable model, not clearly reasoning effort (`output/investigations/20260914-astra-luna/report.md`).
- DeepSeek V4.1 Flash via OpenRouter through Codex passed sandbox checks (0 levels in the side test).
## Decided
- One maintained path: AVO campaigns and the direct Codex player behind the workbench.
## Next
- More models on the hard games (Enqueue, Atlas Shrank, IceCrates, Knightoban).
