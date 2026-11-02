---
date: 2026-10-13
title: Qwen family on Modality, Flash and Max vs 27B
threads: [qwen-harness]
runs: []
commits: []
docs: [docs/research/diary-figures-20261029/qwen-era/fig2_qwen_family_modality.png, docs/research/qwen-modality-max-analysis-20261014.md, docs/research/qwen-modality-claim-audit-20261015.md, docs/research/diary-figures-20261029/qwen-era/README.md]
reconstructed: true
---
## Did
- Ran Qwen 3.8 Flash and Max (`qwen3.8-max-0902`) baseline+ on Modality (100 actions).
- Ran AVO campaigns on Modality for Max, Flash (plus a recovery after an infrastructure interruption) and 27B: high effort, Alibaba routing, same common prompt and budgets.
- Queued AVO for all three models on Enqueue, IceCrates and Knightoban (`output/followups/qwen38-four-games-20261013`); these were stopped by hand.
- `workbench/experiments.py`: unique temp files and retries for manifest writes, so a blocked write no longer kills a job.
## Found
- Baseline+: Max 1/4, Flash 1/4 (27B earlier 0/4) at 100 actions.
- AVO final solvers: Max 4/4 in 265 actions; Flash 1/4; 27B 2/4 (its campaign hit the worker deadline after the evaluation).
## Decided
- —
## Next
- Analyse why Max succeeded and the others did not.
