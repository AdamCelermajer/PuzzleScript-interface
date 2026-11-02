---
date: 2026-08-25
title: Midas campaigns, outer AVO loop and benchmark v0.4
threads: [avo-campaigns, benchmark-curation, proposal]
runs: []
commits: [0270988, 893e0c6, 7d7b8be]
docs: [docs/research/avo-framework.md, avo/evolution/README.md]
reconstructed: true
brief: true
---
## Did
- Checkpointed a month of uncommitted work (`0270988`): AVO core, a `benchmark/` package v0.4 (per-level verified solutions, rule probes, closeness), random and simulated-partial reference agents, and early paper and BIU proposal drafts under `paper/`.
- Ran six AVO attempts on Midas (15 levels, `gpt-5.6-sol` high, 1,000 steps): `avo/output/midas-*-20260825`.
- Added the outer AVO loop over complete agent runs (`avo/evolution/`, `avo/evolve.py`); Aug 26 fixed concurrent tool responses.
## Found
- Midas v01, v05 and v06 each reached 4/15 levels; v03 stopped at level 5 after 794 steps.
- First evolution `midas-live-v01`: best fitness 8 over 5 evaluations; its source run reached 4/15 and no run produced a complete solver (`output/share/midas-solver-sequence-20260828/README.md`).
## Decided
- Benchmark v0.4 scores rule learning (predict `f2` from `<f1, action>`) and closeness to a verified solution; goal recognition is out of v0.4.
## Next
- Evaluate learned solvers in fresh games instead of trusting in-run progress.
