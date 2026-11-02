---
date: 2026-10-28
title: Rule-learning curves against actions, tool calls and tokens
threads: [qwen-harness]
runs: [output/workbench/20261021T144508-vast-fp8-harness2-153a4dc2, output/workbench/20261021T162323-vast-fp8-baseline-v4-6767db38, output/workbench/20261021T144507-vast-fp8-baseline-avo-a08335e1, output/workbench/20261021T151117-vast-fp8-baseline-v2-b3675889, output/workbench/20261021T155237-vast-fp8-baseline-v3-b425ddaf]
commits: []
docs: [docs/research/rule-learning-20261028/rule-learning-knightoban.png, docs/research/rule-learning-20261028/rule-learning-icecrates.png, docs/research/rule-learning-20261028/rule-learning-modality.png, docs/research/rule-learning-20261028/rule-learning-per-game.png, docs/research/rule-learning-20261028/rule-learning.html, docs/research/rule-learning-20261028/README.md, docs/research/rule-learning-20261028/curves.json, docs/research/rule-learning-20261028/rules.json]
reconstructed: false
---
## Did
- Rebuilt every version of `world_model.md` (193 versions, 11 runs of 21 Oct) from the write and edit events in each run's `raw/`, and put each on one axis with tokens, tool calls, game actions and levels.
- Wrote 7 to 8 true rules per game from `script.txt` (Modality, IceCrates, Knightoban), tagged visible or hidden, and had 104 versions graded rule by rule.
- Plotted rules known against game actions, tool calls and generated tokens for the agent-driven and the controller-driven run of each game.
- Checked how reasoning is kept: OpenCode sends past reasoning back only when `interleaved` is set, which our config does not do (`docs/research/opencode-vs-codex-20261020.md`); not yet confirmed on a real request.
## Found
- IceCrates: agent-driven ends at 86% of the rules (6 levels, 320 actions), controller-driven at 64% (3 levels, 271 actions).
- Knightoban: agent-driven 86% (6 levels, 326 actions), controller-driven 43% (0 levels, 451 actions).
- Modality: controller-driven reaches 81% by 226 actions (3 levels); agent-driven 69% after 1000 actions (3 levels). The controller run wrote the floor-colour rule at action 25 (dark and white floor joined only through the checkerboard tile). No run states that pushing also depends on the floor colour.
- The agent-driven player rarely updates its notes: in Knightoban it wrote `world_model.md` at the start and after winning, so its curve undercounts what it knew.
## Decided
- Measure rule learning by the `world_model.md` versions, graded per rule (correct 1, partial 0.5).
## Next
- Hand-check about 20 grades.
- Log one real OpenCode request to confirm whether past reasoning is dropped.
- Design the wiped-context condition: wipe every action or every N; notes pasted into the prompt or read by the agent; controller or agent driver.
