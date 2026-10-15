# Audited Modality results for Max Flash and 27B

Revised 15 October 2026. This revision supersedes the causal explanations in the 14 October version. The previous text is preserved under `output/investigations/qwen-modality-claim-audit-20261015/pre-audit/`.

The [claim-by-claim audit](qwen-modality-claim-audit-20261015.md) is the detailed account of verified evidence, corrections and unresolved questions.

## Established outcomes

| Model | Baseline+ at 100 actions | AVO research progress | Final AVO solver | Final solver actions |
|---|---:|---:|---:|---:|
| Max | 1/4 | 3/4 in 123 actions | **4/4** | 265 |
| Flash | 1/4 | 3/4 in 160 actions | **1/4** | 1,500 |
| 27B | 0/4 | 1/4 in 234 actions | **2/4** | 1,500 |

The new 27B candidate received a completed final solver evaluation, but its overall campaign was cancelled at the worker deadline. Flash's analyzed campaign recovered from an earlier infrastructure interruption. Each recent campaign evaluated one candidate. Earlier 27B attempts remain separate evidence.

The final results agree with the complete action and transition logs. A native-engine replay independently matches all 3,565 saved actions from these six runs, without any player/crate position or completed-level mismatch. Two historical real self-check logs add 135 matching actions, giving 3,700 actions across eight logs. This is deterministic replay of existing evidence in the installed PuzzleScript engine, not a new model experiment.

## What differs between the conditions

Baseline+ supplies persistent note tools, disables shell execution, receives a current grid and attached image, and asks for one next action per decision. Its budget is 100 actions.

AVO supplies a shell-based workspace and asks for an executable solver. Its budgets allow 300 research actions, two real solver self-checks of up to 1,500 actions each, and a final solver evaluation of up to 1,500 actions. Outer and inner model roles use the same model within each campaign. The generated outer strategies differ between models.

Recent AVO runs share the recorded common prompt/profile component hashes and nominal budgets. Outbound requests confirm high effort and Alibaba routing with fallbacks disabled. Complete instruction strings differ because they include different candidate strategies. The baseline+/AVO comparison does not match total resources, tools, instructions or output requirements.

The recorded scores are higher under AVO for Max and 27B and equal for Flash. Whether AVO itself caused an improvement, and which component matters, remain unmeasured.

## Verified observations about the generated programs

**Max.** Its program reads the latest frame, identifies visible roles from sprite colors, performs breadth-first search in a learned transition model, and emits one action at a time. It uses two real solver self-checks. The first exits before taking an action with `KeyError: metadata`; the second wins 4/4 in 265 actions. The final evaluation repeats 4/4 in 265 actions. Its chosen actions contain no position no-ops. This establishes a successful artifact, not a complete explanation of its advantage.

**27B.** Its final parser reads `frame[0]`, which the runtime's before/after response makes the older frame. Its notes and code explicitly model delayed action effects. Its local simulator implements that theory and contains synthetic later levels; local tests announce four completed mock levels. Its actual final solver completes two real levels. It takes 1,420 actions on level 3, including 1,405 position no-ops, and uses neither available research self-check. The one-line latest-frame-only intervention scores 1/4 in the analyst's offline simulator, so that intervention does not establish a complete repair.

**Flash.** Its final program reads the latest frame and learns representations and rules online. Its research episode reaches three levels, but its final solver reaches one and then spends 1,490 actions on level 2, including 740 down and 736 up. Offline replay reproduces the entire recorded sequence. The program has a visit-key mismatch and unresolved goal-object handling. Isolated corrections tested in the offline simulator do not solve it. Research progress does not establish that Flash could compile a successful solver, and these code observations do not establish the full cause of its failure.

## The historical AVO comparison

The inspected 30 September 27B attempt did use real validation: one check scored 0/4 in 120 actions, and another scored 1/4 before the solver crashed after 15 actions. Its settings differ from the recent campaigns, including inner effort, time limit, evaluation allowance and archived prompt hash. Therefore a story that Max won because AVO only recently began using real validation is unsupported.

The recent shared instructions explicitly request real self-checks, but Flash and 27B do not invoke them before their research timeouts. Max does. This is a recorded behavioral difference. Why it happens has not been isolated.

## Rule accuracy and task success

Max's model is not fully correct. It treats grey as a global phase-toggle button; the game source instead applies local terrain compatibility. At its recorded decision states, native engine branches confirm 32 wrong directional predictions among 1,060 tested alternatives, counted with repeated states. All chosen actions in the winning trajectory work.

This verifies both the win and errors in its model. It does not establish generalization to new layouts or a complete description of the game. Its successful real self-check already plays all four fixed levels before the final evaluation.

## Claims not supported by this experiment

- A parameter-count or pretraining explanation of the score gap.
- A general baseline+ versus AVO ranking under matched resources.
- An inability of 27B or Flash to solve the task under another procedure.
- An ability of Flash to produce a successful solver inferred solely from 3/4 research progress.
- A causal explanation attributing Max's success to one strategy, implementation choice or validation step.
- A demonstration that multiple AVO generations helped; only one candidate was evaluated per recent campaign.
- A framework fix that explains old-versus-new instruction-following behavior.

Flash also should not be described as simply smaller than 27B. The [published Flash specification](https://docs.qwencloud.com/developer-guides/getting-started/latest-model) lists a 125B main model with 6B active parameters, while [27B is dense](https://huggingface.co/Qwen/Qwen3.8-27B). Model names and provider pins do not identify exact hosted weights or serving precision.

## Evidence and reproduction

The full audit links the precise runs and corrections. Its scripts and structured evidence are in `output/investigations/qwen-modality-claim-audit-20261015/`: `collect.py`, `native_verify.cjs`, `facts.json`, `source-hashes.json`, `evidence-manifest.json`, `native-verification.json` and `historical-comparison.json`.

The earlier offline code interventions remain in `output/investigations/qwen-modality-20261014/`. They are explicitly simulator findings, not real-service tests of modified solvers.

No paid model runs or production service sessions were launched for the audit. Original run artifacts are preserved. The remaining paid queue stays cancelled.
