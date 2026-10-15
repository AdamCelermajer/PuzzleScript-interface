---
date: 2026-10-15
title: Claim audit of the Qwen Modality results
threads: [qwen-harness, avo-campaigns]
runs: []
commits: [94086fe]
docs: [docs/research/qwen-modality-claim-audit-20261015.md, docs/research/qwen-modality-yoav-brief-20261014.md, docs/research/qwen-modality-max-analysis-20261014.md]
reconstructed: true
---
## Did
- Audited each claim in the Modality analysis and replayed every saved action in the native PuzzleScript engine.
- Revised the analysis and the supervisor brief; the pre-audit text is kept under `output/investigations/qwen-modality-claim-audit-20261015/pre-audit/`.
- Added the `image` gateway tool and made `max_wall_seconds=0` mean unlimited.
- Stopped the overnight NanoGPT runs by hand.
## Found
- Zero mismatches across 3,565 saved actions in six logs; the recorded scores hold.
- Baseline+ and AVO differ in tools, budgets, instructions and output, so they are not a matched comparison.
- NanoGPT baseline+ (1,000-step budget, stopped by hand): 27B thinking 1/4 in 386 actions, Flash 2/4 in 296 (`output/followups/qwen38-modality-nanogpt-20261015/conclusion-replay.json`). NanoGPT AVO 27B: final solver 0/4 (solver exited with an error).
## Decided
- Withdrew the causal explanations (that AVO, or a framework fix, caused the better results); outcomes and program behaviours stay, explanations become hypotheses.
- No further paid runs scheduled for now.
## Next
- Test explanations as explicit interventions, not from artifacts.
