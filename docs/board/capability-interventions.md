---
title: Does improving a specific capability make the smaller models solve the games?
status: todo
order: 2
threads: [qwen-harness]
links:
  - "Capability scorecard notes | docs/research/capability-scorecard-modality-20261015.md"
runs: []
---
## Question
If a weak capability of Flash or 27B is supported directly, do they then solve the games Max solves?

## Current answer
Not tested. The scorecard ranks candidate interventions. They are designs only; no runs are scheduled.

## Evidence
1. Require a real self-check before finishing (verification). Test: 27B and Flash, AVO, 3 runs each, against current AVO.
2. Show only the latest frame (perception). Test: 27B, AVO, 3 runs against 3 controls.
3. Add a rival-hypothesis step with a deciding experiment (rule induction, action interpretation). Test: 27B and Flash, baseline+.
4. Ranks 4–8:
   - supplied action meanings
   - supplied goal
   - research results carried into the solver
   - supplied mechanics with a planner
   - a watchdog for actions that don't move the player

The watchdog can be checked offline on existing logs at no cost.

## Next
- Choose which interventions to present as the proposal's experiments.
