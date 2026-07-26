# Todo

## Agent Correctness

- Investigate the logical-rule bug where a state difference was not registered.
- Review the design issue where rule inference was performed on exploratory actions without separating intended effects from incidental effects.
- Add a regression test once each failure mechanism is understood.

## Prompting

- Tighten the rule-induction prompts.
- Make the distinction between a natural-language hypothesis and a verified executable rule explicit.
- Require the model to identify uncertainty instead of filling missing mechanics with assumptions.

## Benchmark Paper

- Freeze the central claim: controlled capability decomposition, not simply a new collection of PuzzleScript games.
- Define the first information conditions: image, anonymous grid, labeled symbolic state, provided goal, and provided rules.
- Decide how goal-recognition difficulty will be measured from evidence rather than assigned subjectively.
- Add contamination controls: hide titles, permute symbols and colors, and create private or mutated held-out games.
- Check redistribution and licensing for every selected human-authored PuzzleScript game.
- Run random, oracle search, direct LLM, ReAct-style, and rule-learning baselines.
- Produce the competitor matrix, capability-decomposition diagram, information-condition results, and goal-recognition evidence curve.

## Immediate Paper Decisions

- Choose the benchmark name and paper title.
- Select the deterministic benchmark subset.
- Separate mechanic complexity from level planning depth.
- Define behavior-based rule equivalence tests.
- Treat the existing 50-game goal-recognition experiment as pilot evidence unless the human sample is expanded.
