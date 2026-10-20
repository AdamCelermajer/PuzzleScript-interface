---
title: Does improving a specific capability make the smaller models solve the games?
status: todo
order: 2
threads: [qwen-harness]
links:
  - "Capability scorecard notes | docs/research/capability-scorecard-modality-20261015.md"
  - "Board claim verification (19 Oct) | docs/research/board-claim-verification-20261019.md"
runs: []
---
## Question
If a weak capability of Flash or 27B is supported directly, do they then solve the games Max solves?

## Current answer
Not tested. The scorecard ranks candidate interventions. They are designs only, no runs exist after 15 Oct, and each targets a behaviour seen in a single run per model. Two offline facts bound expectations: patching 27B's solver to read the latest frame scored 1/4 in the offline simulator (down from 2/4), and Flash's solver already re-learned the movement rule online and still failed, so neither "latest frame" nor "carry the rule into the solver" is a demonstrated fix.

## Evidence
1. Require a real self-check before finishing (verification). Test: 27B and Flash, AVO, 3 runs each, against current AVO. Basis: Max ran two real checks and won; Flash and 27B ran none. One run each.
2. Show only the latest frame (perception). Test: 27B, AVO, 3 runs against 3 controls. Basis: 27B's parser reads `frame[0]`. The offline parser patch alone scored 1/4.
3. Add a rival-hypothesis step with a deciding experiment (rule induction, action interpretation). Test: 27B and Flash, baseline+. Basis: 27B called undo a "jump" and Max never tested grey-to-original-colour moves.
4. Ranks 4–8:
   - supplied action meanings
   - supplied goal
   - research results carried into the solver
   - supplied mechanics with a planner
   - a watchdog for actions that don't move the player

The watchdog can be checked offline on existing logs at no cost; the offline simulator reproduces every recorded action sequence exactly.

## Next
- Choose which interventions to present as the proposal's experiments.
