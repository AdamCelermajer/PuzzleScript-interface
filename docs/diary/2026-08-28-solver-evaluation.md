---
date: 2026-08-28
title: Fresh-game solver evaluation for AVO on Midas
threads: [avo-campaigns]
runs: [avo/output/evolution/midas-solver*, avo/output/evolution/midas-outer-sol-high*]
commits: [dda47d8, 82148b7, 358d86c, 621d757, 4a7ba31, 82a1afa, cf8ffbb]
docs: [avo/evolution/README.md]
reconstructed: true
---
## Did
- Learned solvers are now evaluated in a fresh game from a trusted workspace archive, with fresh observations streamed through evaluation.
- Isolated the outer optimizer; separated generation and research/evaluation budgets; kept restricted sandboxes after evaluation.
- Aug 27: eight Sol/Sol solver campaigns (4-evaluation cap). Aug 28: Luna inner / Sol outer, model-first and Spark variants. Aug 31: three Sol/Sol campaigns with 300–500 research steps.
## Found
- Best Midas result: `midas-outer-evidence-luna-medium-sol-high-20260828T210529`, 6/15 levels after 30 evaluations (budget exhausted); solvers bundled in `avo/output/compiled/midas-breakthrough-solvers-20260829`.
- Aug 27 campaigns recorded best fitness 4–8; Aug 31 campaigns each reached fitness 4. The Spark run hit its context window and then a usage limit.
## Decided
- Fresh-solver score, not research progress, is the campaign fitness.
## Next
- Move to a multi-game set and stronger isolation.
