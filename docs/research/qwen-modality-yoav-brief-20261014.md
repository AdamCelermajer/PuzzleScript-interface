# Verified Modality findings for the meeting with Yoav

Revised 15 October 2026 following the claim-by-claim audit.

## What to say

“I have one verified full Modality success from Qwen Max under AVO. Its generated standalone solver completed all four fixed levels from a fresh reset in 265 actions. Flash's final solver completed one level; the new 27B solver completed two.

“The baseline+ pilots, each limited to 100 direct actions, scored one level for Max, one for Flash and zero for 27B. The AVO condition additionally allows research, coding and solver self-checks, so I am not presenting this as a matched-resource causal comparison.

“I audited the original results and replayed their saved action sequences in the actual PuzzleScript engine. The scores check out. I also identified concrete differences in the generated programs and validation behavior, but I have not established which differences caused the outcome gap.”

## Numbers

| Model | Baseline+ | Research progress in AVO | Final autonomous solver |
|---|---:|---:|---:|
| Max | 1/4, 100 actions | 3/4, 123 actions | **4/4, 265 actions** |
| Flash | 1/4, 100 actions | 3/4, 160 actions | **1/4, 1,500 actions** |
| 27B | 0/4, 100 actions | 1/4, 234 actions | **2/4, 1,500 actions** |

The 27B candidate evaluation completed; its surrounding campaign hit the worker deadline. Each recent campaign evaluated one candidate. These are individual outcomes, not estimated success rates.

## What is established about AVO

- Max used two real solver self-checks, scoring 0/4 and then 4/4. Its final real evaluation also scored 4/4.
- Recent Flash and 27B used no research self-checks before timing out. Both still received a trusted final solver evaluation.
- 27B's local simulator contains invented delayed-action mechanics and synthetic later levels. Its mock success does not count as real success.
- The inspected September 30 27B attempt did use real self-checks: 0/4 and then 1/4 with a solver crash. We cannot claim that real validation was newly introduced or that a framework fix explains Max's success.

## What remains open

Flash's 3/4 research progress does not prove it could generate a working solver. The final artifact failed to reproduce that progress. 27B's older-frame parser and delayed-action theory are documented, but a complete cause of failure is not established. Neither result proves incapability.

Max's win is real, but its written model is imperfect: native counterfactual tests find 32 wrong predictions among 1,060 directional alternatives at recorded decision states. This is not a held-out-layout generalization result.

The project objective remains reliable rule learning and solving with small models. The evidence currently establishes outcomes and specific program behaviors; explanations and proposed interventions remain hypotheses until tested. No further paid runs are scheduled.

[Full claim audit](qwen-modality-claim-audit-20261015.md) · [Corrected detailed analysis](qwen-modality-max-analysis-20261014.md)
