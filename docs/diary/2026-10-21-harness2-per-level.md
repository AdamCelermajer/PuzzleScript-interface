---
date: 2026-10-21
title: Harness² per level with an escalating budget
threads: [harness2, qwen-harness, workbench]
runs: [output/workbench/20261021T235821-harness2-per-level-modality-b20130e2]
commits: []
docs: [docs/research/harness2-per-level-feasibility.md, docs/research/per-level-interface.md]
reconstructed: false
brief: true
---
## Did
- Harness² option `levels` (N > 0): levels 1..N in order, each its own task in `levels/L<k>/rounds/R<n>/` (`frameworks/harness2/run.py` `run_levels`); the player plays `--start-level k --stop-after-levels 1 --max-steps B`.
- A round is one k=1 cycle (base1 in the level's first round only, INV and DOM side by side, then agg1), with no final rollout. An unsolved round moves to the next value of `budgets` (default 30,50,100,200,500; the last value repeats) and stops at `max_rounds` (default 5). A level starts from the previous level's kept harness and at the budget the previous level ended on, so the budget never goes down. `skip_below_shortest` (off) skips budgets below `frameworks.levels.shortest`.
- Kept harness within a round, among rollouts at its budget: solved first, then fewer actions, then the starting harness. With no solve, agg1 > inv1 > dom1 > base1.
- A rollout whose harness (fingerprint) and budget were already played in the level is not replayed (`reused.json`). A level that errors is recorded and the run goes on.
- Run page: a level strip, the rounds of the picked level, its kept harness, and that round's rollouts and coach sessions (`workbench/harness2_view.py` `levels`, `Harness2Detail.tsx`). Catalog progress counts rollouts across levels.
- Launched one run on Modality L1-4: OpenCode, `openrouter/qwen/qwen3.8-27b` as player and coach, both at effort high, pinned to `near-ai` with fallbacks off, against the level instance on 8002.
## Found
- Tests: 27 Harness² tests (fake player and coach: escalation, carry-over, reuse, cap, broken level, resume, view) and 316 Python + 58 frontend tests pass.
## Decided
- Round cap 5 per level (Adam asked for a cap but left the number open). The unsolved-round tie order (composer first) is our call, so that edits carry forward across rounds.
## Next
- Read the run when it ends: rounds per level, which stage was kept, and whether carried harnesses help later levels.
