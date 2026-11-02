---
date: 2026-09-22
title: Astra and DeepSeek Flash campaigns on the hard games
threads: [avo-campaigns]
runs: [output/workbench/20260923T*, output/workbench/20260924T*, output/deepseek-max-trace-probe-20260923*]
commits: []
docs: [docs/research/diary-figures-20261029/avo-era/fig2_games_levels_vs_tokens.png, docs/research/diary-figures-20261029/avo-era/fig5_tokens_overview.png, docs/research/three-game-mechanics-demo.md, docs/research/diary-figures-20261029/avo-era/README.md]
reconstructed: true
---
## Did
- Sep 22: GPT-6 Astra (low, both roles) on IceCrates, Portal Ban, Enqueue and Atlas Shrank.
- Sep 23: DeepSeek V4.1 Flash (max) via OpenRouter on Modality, Knightoban and IceCrates; short trace probes.
- Sep 24: Enqueue with GPT-6 Luna and DeepSeek Flash.
## Found
- Astra: IceCrates 6/6 and Portal Ban 5/5 in both world-model modes; the Enqueue and Atlas campaigns were stopped by hand.
- DeepSeek Flash: Modality 4/4, IceCrates 6/6 (job marked failed only because the final report was missing), Knightoban 6/6 on rerun after an isolation "private path" error.
- Enqueue: GPT-6 Luna reached 8/14 after 20 evaluations (budget exhausted); DeepSeek reached fitness 8 before an isolation error.
- Infra errors seen: "gpt-6-sol not supported with ChatGPT account", "Unapproved model tool: get_goal".
## Decided
- —
## Next
- A small open model: Qwen 3.8-27B.
