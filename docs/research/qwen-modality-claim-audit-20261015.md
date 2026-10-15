# Audit of the Modality comparison claims

Audit date: 15 October 2026. This corrects the explanations previously given to Adam. Scores, artifact observations, offline interventions and untested explanations are different kinds of evidence; they must not be substituted for one another.

## Verified run outcomes

| Model | Baseline+ result | AVO research progress | AVO final solver result | Final solver actions |
|---|---:|---:|---:|---:|
| Max | 1/4 after 100 actions | 3/4 after 123 actions | **4/4** | 265 |
| Flash | 1/4 after 100 actions | 3/4 after 160 actions | **1/4** | 1,500 |
| 27B | 0/4 after 100 actions | 1/4 after 234 actions | **2/4** | 1,500 |

Each baseline result agrees with its complete transition log and action list; all three ended with `step_budget_exhausted`. Each final AVO solver result agrees with its trusted evaluation JSON and full evaluation transition log. The 27B candidate evaluation completed, but the surrounding campaign was cancelled at the worker deadline and has no final outer summary. Flash's research run was a recovery from an earlier infrastructure interruption. These are single recorded runs, not estimates of model success rates.

The native-engine audit replays every action from these six logs in the actual installed PuzzleScript npm engine, using the real Modality source. It compares player position, crate position and completed-level count against the original records. Across **3,565 saved actions there are zero mismatches**. This check runs in memory, without opening a server, contacting a model or writing to production game history. It verifies the recorded outcomes on the current source and engine version; it is not a new model experiment or a statistical replication.

## Baseline+ and AVO are different experimental conditions

The archived baseline+ manifests enable persistent note tools and disable shell execution. The model chooses one game action per decision, receives a current grid and an attached image, and has a 100-action budget. It is not asked to deliver an executable solver.

AVO provides a shell-based research/implementation workspace and a different task: produce `solver.py` for execution without further LLM reasoning. The recorded budgets allow 300 research actions, two real solver self-checks of up to 1,500 actions each, and a final solver evaluation of up to 1,500 actions. A model also supplies the outer research strategy. Each of the three recent campaigns actually evaluated one candidate, although three were allowed.

The recent AVO run configs match on their common profile/base-prompt hashes, pinned Alibaba routing, high effort and nominal budgets. Captured outbound requests confirm the intended model IDs, `reasoning.effort=high`, and Alibaba routing with fallbacks disabled. The actual inner instruction strings are **not identical**: they include different model-generated candidate strategies. Same common prompt component does not mean identical complete experimental instructions.

The first 100 final AVO solver actions reach Max 2/4, Flash 1/4 and 27B 2/4. Those prefixes are measurable from the saved logs, but they come after research and implementation. They are still not a control matched to 100 direct baseline actions.

The supported comparison is: these AVO solver artifacts score higher for Max and 27B, and the same for Flash, than the respective 100-action baseline+ pilots. **The causal effect of AVO, the effect of extra resources, and the contribution of individual components have not been isolated.**

## Corrections to the previous answers

| Previous statement or implication | Audit disposition | What the evidence actually permits |
|---|---|---|
| Max solved Modality; Flash and 27B did not | Verified | Max 4/4; Flash 1/4; the new 27B candidate 2/4 in final real evaluations. |
| AVO helped or enabled Max, and improved 27B | Causal wording withdrawn | The scores differ under different workflows and budgets. The experiment does not isolate why. |
| Baseline+ is generally worse than AVO | Unsupported generalization | This table describes these runs on Modality. There are no matched-resource repeats establishing a general ranking. |
| Flash reached 3/4, so it could have produced a solver for those levels | Not demonstrated | Research progress is real. A solver compiling/reproducing that research behavior has not been tested. Its actual delivered solver scores 1/4. |
| Flash failed because it tried to relearn mechanics online | Untested explanation | Its final code does learn online; Max's embeds learned constants/rules. No intervention establishes that this architectural difference caused the score gap. |
| 27B cannot solve this task | Not demonstrated | These attempts fail to solve it. They do not establish inability under another strategy, correction or random outcome. |
| 27B reads an older observation and models delayed actions | Verified code observation | Its parser uses `frame[0]`; the runtime emits before/after frames in that order. Its notes and code explicitly use delayed-action mechanics. |
| Reading the older frame is the complete cause of 27B's failure | Not demonstrated | A latest-frame-only intervention scores 1/4 in the analyst's offline simulator, versus 2/4 unchanged. It does not isolate the origin of all learned errors or supply a complete repair. |
| Flash's visit-count bug explains the loop | Not demonstrated as a cause | The mismatched keys are a code defect. The isolated correction leaves its entire final action sequence unchanged. |
| AVO stopped allowing invented simulators this time | False | The current 27B artifact includes a simulator with its delayed-action theory and synthetic later levels. Native evaluation, not its mock score, records 2/4. |
| The old AVO run failed because it never used real solver checks | False for the inspected September 30 attempt | It used two real checks: 0/4, then 1/4 with an early solver crash. |
| Max's success proves that a framework fix corrected instruction following | Not demonstrated | Recent Max uses both real checks; recent Flash and 27B use none. No controlled framework-change experiment explains that difference. |
| Max followed every instruction correctly | Not established | Specific behaviors are verified, especially its real checks and final win. Complete instruction compliance is not an evaluated outcome here. |
| Max recovered the game's true mechanics | False as a complete claim | Its global-phase model disagrees with the real engine on 32 of 1,060 directional alternatives at recorded decision states. |
| Max's win is only a result inside its own simulator | False | The trusted final evaluator scores real-game progress, and native replay confirms all four levels. |
| Max demonstrated generalization to an unseen fourth level | Not established | Level 4's initial board is observed during research, and a self-check reaches all four levels before final evaluation. |
| This demonstrates the benefit of repeated AVO evolution | Not established | Each recent campaign has only one evaluated candidate. |
| Flash is simply smaller than 27B | Misleading; withdrawn | Published specifications distinguish a 125B Flash main model with 6B active parameters from a dense 27B model. This is not a clean single-architecture size comparison. |
| Model size or pretraining explains the result | Untested | Neither parameter count, architecture nor training differences were experimentally isolated. |

## What the current and historical AVO artifacts establish

The recent common inner instructions explicitly ask the model to align actions to current observations, validate simulations against real transitions, and invoke `evaluate_solver` before finishing. The instruction requirement is verified in the captured outbound requests. It is not an enforced guarantee that every model will do so before a timeout.

Recent Max uses both real solver self-checks. Check 1 executes zero actions, exits with code 1 and records a `KeyError: metadata` while parsing the evaluator's wrapped input. Check 2 completes four levels in 265 actions, exits with code 0 and has empty stderr. The subsequent final evaluation also completes four levels in 265 actions.

Recent Flash and 27B have no `solver_self_check_completed` events and no research self-check result directories. Their final programs are still executed by the trusted evaluator after research. Flash scores 1/4 and 27B 2/4. Their local test outputs are not used as those final scores.

The inspected historical attempt is `20260930T183705-133bda45`. Its real self-checks record:

| Historical real check | Requested action cap | Actions actually taken | Score | Termination |
|---|---:|---:|---:|---|
| Check 1 | 120 | 120 | 0/4 | Budget completed, return code 0 |
| Check 2 | 400 | 15 | 1/4 | Solver exited early, return code 1 |

The native replay also matches all 135 historical self-check actions and their level counts. With these included, the audit covers **3,700 saved actions in eight logs**, all without position or level-count mismatches.

This older campaign uses medium effort for the inner player, a 19,800-second limit and 15 allowed evaluations; the recent ones use high effort, a 10,800-second limit and three allowed evaluations. The archived base-prompt hashes also differ. These differences prevent a claim that the old-versus-new comparison isolates a framework fix or a model-compliance change. This historical inspection does not identify every older attempt the user might have meant.

## Max's incorrect rules and the audit's own limitations

The recorded Max program models grey as a global phase-toggle button. The source actually prohibits direct white-to-black and black-to-white player movement, with grey acting as a bridge. At recorded decision 3 on level 1, the player is on grey at (1,2). Max predicts that moving right back to dark at (1,3) is blocked. The real npm engine permits that move.

The earlier analyst audit used a hand-written interpretation of the source rules and Max's parser. That was not fully independent of the generated code. This audit adds a native check: for each of Max's 265 recorded decision states, restore the real engine state and test all four directional actions. Native results confirm **32 model disagreements out of 1,060 alternatives**, including repeated decision states. This confirms a model error on those alternatives, not an estimate of error over all possible game states.

The previous latest-frame and planner ablations remain **offline simulator results**. Unchanged solver trajectories were reproduced exactly before those interventions, but that does not validate the simulator over every new state reachable after a modification. They are useful diagnostic observations, not real-service reruns or proofs of the complete failure cause.

The actual model weights and serving precision cannot be established from a configured API model name or provider pin. Published Flash architecture specifications can clarify model-size terminology, but do not provide a weight checksum for the hosted requests used here. Official specifications: [Qwen 27B model card](https://huggingface.co/Qwen/Qwen3.8-27B), [QwenCloud Flash documentation](https://docs.qwencloud.com/developer-guides/getting-started/latest-model), and [Flash Next architecture description](https://github.com/QwenLM/Qwen3.8-Flash-Next/blob/main/README.md).

## Reproducibility and scope

The audit inventory is in `output/investigations/qwen-modality-claim-audit-20261015/`:

- `facts.json`: fields extracted from original configs, results and traces.
- `source-hashes.json`: SHA-256 hashes for the inspected primary evidence files.
- `evidence-manifest.json`: saved actions, state expectations and Max's model predictions.
- `native-verification.json`: native-engine replay and counterfactual results.
- `collect.py` and `native_verify.cjs`: reproducible extraction and engine verification.
- `historical-comparison.json`: the inspected September 30 settings and self-check results.
- `pre-audit/`: the two earlier reports, preserved before correcting them.

No new model runs, paid requests or production service sessions were launched. The original run artifacts and solvers are unchanged. The paid queue remains cancelled. Proposal source and Overleaf were not edited during this audit.

The established result is a real Max success alongside partial Flash and 27B results. Whether another procedure would make either smaller-active model solve the task remains an unanswered experimental question.
