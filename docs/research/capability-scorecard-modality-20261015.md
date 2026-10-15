# Capability scorecard: Qwen 3.8 Max, Flash and 27B on Modality

15 October 2026. This report uses existing evidence only. No model runs, paid calls or service sessions were started for it. It uses the seven capabilities in the proposal (`docs/proposal/main.tex`, Table `tab:challenge`) plus one process row, **verification and grounding**. All of it follows the [claim audit](qwen-modality-claim-audit-20261015.md): the ratings describe behaviour that was recorded, not the causes of the score gaps. The machine-readable version is [`capability-scorecard-modality-20261015.json`](capability-scorecard-modality-20261015.json).

## Scope and caveats

- **One recorded run per model and condition.** These are not success rates. Each AVO campaign evaluated one candidate.
- **The conditions are not matched.** Baseline+ is direct play: 100 actions, note tools, no shell. AVO is research plus a solver: 300 research actions, up to two real self-checks and a final evaluation of up to 1,500 actions, a shell, and a strategy written by the model. Each cell gives the AVO and baseline+ ratings separately where they differ.
- **The 27B baseline+ run is older** (`20261008T112945-f705fa9a`, 8 Oct). The Max and Flash baseline+ runs are from 13 Oct. All of them use Alibaba routing and high effort.
- **Level 4 is not held out.** Its initial board was visible at the end of Max's research. Max's real self-check 2 then played all four levels before the final evaluation.
- **Ratings come from the analyst's reading of the artifacts.** A second annotator has not checked them. "Rule accuracy" is judged against the game source and the native counterfactual audit.
- **Other runs exist but are not scored here.** These are earlier 27B runs (30 Sep to 1 Oct) and the NanoGPT runs from 15 Oct, which were stopped by hand (27B 1/4 in 386 actions, Flash 2/4 in 296). Their providers and budgets differ from the runs above.

Recorded outcomes (from the audit): baseline+ gave Max 1/4, Flash 1/4 and 27B 0/4. AVO final solvers gave Max **4/4** in 265 actions, Flash 1/4 in 1,500 and 27B 2/4 in 1,500. AVO research progress was Max 3/4 in 123 actions, Flash 3/4 in 160 and 27B 1/4 in 234.

## Scorecard

Ratings use four levels: strong, partial, weak, and none (no evidence). Where a cell shows "AVO / B+", the first rating is from AVO and the second from baseline+.

| Capability | Max | Flash | 27B |
|---|---|---|---|
| Perception | **strong** | **strong** (after self-correction) | **weak** (AVO) / partial (B+) |
| Action interpretation | **strong** | partial (AVO) / strong (B+) | **weak** |
| Rule induction | partial | partial | **weak** |
| Goal recognition | strong (AVO) / **weak** (B+) | **strong** | partial |
| Planning | **strong** | weak (final solver) / partial (research, B+) | **weak** |
| Transfer | strong, but not held-out | partial | **weak** |
| Credit assignment | strong (AVO) / **weak** (B+) | strong (B+) / partial (AVO) | **weak** |
| Verification and grounding (process) | **strong** | **weak** | **weak** (recent run); used real checks on 30 Sep |

Paths below are relative to `output/workbench/` unless stated otherwise. The shorthand is:

- `MAX` = `20261013T152559-avo-max-92c30e52/run-0001/campaign`
- `FL` = `20261013T173422-avo-flash-modality-recovery/run-0001/campaign`
- `Q27` = `20261013T165330-avo-27b-modality/run-0001/campaign`
- `INV` = `output/investigations/qwen-modality-20261014`
- `AUD` = `output/investigations/qwen-modality-claim-audit-20261015`

### Perception

- **Max, strong.** Max noticed that the observation is a two-frame window: its notes say "first diff attempt compared stale frame[0]" (`MAX/x_0001/solver/NOTES.md`). Its solver parses `frame[-1]` (`solver.py:48`). The player sprite has an orange band of the same colour as the crate, and Max resolved that aliasing by matching full sprite colour sets (`MAX/world_model.md`, "Observation quirks"). In baseline+ it identified the composite IDs for the player on dark, checker and white tiles (strategy v10, `20261013T150245-989f6c8b`).
- **Flash, strong after a self-correction.** In research it first read `layer[0]`. It retracted that ("Reading layer[0] was a decoding bug and is retracted", `FL/x_0001/solver/solver.py` docstring, belief 1) and switched to PNG-decoded and last-layer states (research rationales "true-state research (PNG decoded)" and "verifying prediction vs last-layer frame"). In baseline+ it identified the player-on-terrain composite IDs by step 8.
- **27B, weak in AVO and partial in baseline+.** Its final parser reads `obs["payload"]["frame"][0]` (`Q27/x_0001/solver/solver.py:107`), which is the older frame. Its own docstring says that `frame[0]` is stale after level transitions, but it kept that parser. The offline snapshots show the solver's believed player position differing from the real one at steps 10 and 100 (`INV/deep-checks.json`). In baseline+, where only the current grid is supplied, it tracked coordinates correctly. The audit's limit applies: patching it to read the latest frame scored 1/4 in the offline simulator, so this error is not shown to be the whole cause.

### Action interpretation

- **Max, strong.** In baseline+ it confirmed ACTION7 = undo at T12. At T47 it ran a test that tells undo apart from a rival "character swap" model, and the swap model failed (strategy v16). In AVO it mapped ACTION1–4 and ACTION7 = undo by research events 4–17 (`MAX/world_model.md`).
- **Flash, partial in AVO and strong in baseline+.** In baseline+ it confirmed undo twice (T15–16) and used it to recover a crate it had pushed the wrong way (strategy v20). In AVO research it only began testing "ACTION7 = undo" in the last few actions (research rationales near the end). The final solver calibrated ACTION7 as a one-cell left move, then dropped it: "ACTION7 duplicates ACTION3 … never planned" (`INV/deep-checks.json`). The delivered program therefore cannot undo a mistake.
- **27B, weak.** In baseline+ it read ACTION7 as "JUMP 1 tile opposite last move" and pressed it 13 times. After a dead-end push at t23 it concluded "No reset exists", so a recoverable mistake became permanent (`20261008T112945-f705fa9a` notes). In AVO its model makes each move's direction depend on the previous action, with ACTION7 meaning the opposite of that direction (model M5 in `Q27/x_0001/solver/NOTES.md`). The proposal names exactly this case: misreading undo can make a recoverable error look permanent.

### Rule induction

The true rule: the player cannot step directly between white and black floor. Grey is compatible with both. A push happens only when the player and the crate are on the same kind of terrain.

- **Max, partial, but the most predictive model.** Max explicitly falsified "dark = wall", "checker = decoration", "pushes ignore phase" and "blue ring solid", and its model replays 122/122 recorded transitions (`MAX/x_0001/solver/agent_transcript.jsonl`). However, the model makes grey a global phase-toggle button. Native counterfactuals find 32 wrong predictions among 1,060 alternatives, and the listed examples all start on grey (`AUD/native-verification.json`). Its model fits every recorded transition yet is wrong on grey-to-back moves, so no recorded transition separated a global phase from local terrain compatibility. In other words, the discriminating experiment was never run. In baseline+ it reached 33 hypotheses ("hidden passage", "hidden boxes") and never found the colour rule.
- **Flash, partial: content close to correct, but never consolidated.** Its research planner `FL/x_0001/solver/exp/plan.py` encodes `allowed(a,b) = not ({a,b}=={'dark','white'})`. That is the source's player-movement rule, with the checker compatible with both colours, and Flash used it to plan research levels 2–3. The online-learned pair table in the final solver converges to the same white/dark exclusion (`INV/deep-checks.json`, field `pair`). None of this was written down: `NOTES.md` and `world_model.md` are byte-identical to the seed, and the campaign world model still says that nothing was confirmed (`FL/world_model.md`). In baseline+ it built per-edge "directional entrance" and "gate" maps plus an "invisible box" idea, not a global rule.
- **27B, weak.** Its rules invent hidden state: a last-action variable `b`, a direction `d`, a `d7moved` flag, "first action absorbed" and spontaneous "episode resets". Walls are learned as a per-edge door map rather than a terrain rule. The model was "verified against ALL 143 observed transitions", but those transitions came from the stale-frame data, so it agreed with its own misreading (`Q27/x_0001/solver/NOTES.md`). It did write explicit retractions and ran structured experiments ("E-map", "E-cycle"), but they tested cycle and cooldown theories rather than the terrain rule. In baseline+ it proposed jump, pit and trampoline theories.

### Goal recognition

- **Max, strong in AVO and weak in baseline+.** In AVO it stated: "Pushing a crate onto the blue target wins the level immediately" (`MAX/world_model.md`). In baseline+ it believed "L1 win: enter orange-hollow from below". On level 2 it called the crate "door ID8" and tested the blue tile and the map edges as exits (strategy v16, T41–T83). That run ended at 1/4.
- **Flash, strong.** In baseline+: "L1 win = orange box on the blue target decal". In AVO the final solver confirmed the goal key "orange-ring identity on blue-target identity" from the level-1 win (`INV/deep-checks.json`, field `goal` at step 80).
- **27B, partial.** In baseline+ it said "Target almost surely = blue (0,0)", but only after it had already deadlocked the crate. In AVO its notes say "Win condition UNKNOWN" after 143 actions, with "push RING onto blue" as the leading hypothesis. The final solver's goal is a time-shifted "pose" (ball next to blue, player on the opposite side, next action completes), plus ball-on-blue.

### Planning

- **Max, strong.** It plans with BFS over (player, crate, phase) and replans from every live observation. Over 265 actions none of its chosen actions is a position no-op (`INV/audit.json`). Its research plans executed with "0 unexpected transitions" (NOTES).
- **Flash, weak in the final solver and partial in research and baseline+.** Its research plans won levels 2–3. The final solver spent 1,490 actions on level 2, including 740 down and 736 up moves, and made 732 fallback calls. Offline, correcting the visit key and fixing the goal both left it at 1/4 (`INV/offline-ablation.json`). In baseline+ it found a correct 13-action plan for level 2 but had only 3 actions left.
- **27B, weak.** The final solver used 1,420 actions on level 3, including 1,405 position no-ops; ACTION1 alone was chosen 1,400 times (`INV/audit.json`). With an empty plan its code returns `"ACTION1"` by default (deep-check snapshots show `plan_length` 0 at steps 500 and 1500). In baseline+ it pushed the crate into a corner at t23. In research, 52 of its 151 level-1 actions were no-ops.

### Transfer

- **Max, strong, but not held-out.** One rule-based solver of 233 lines, with no per-level layouts or action scripts, solved levels 2–4. Level 4 took 160 actions with 0 no-ops. Level 4 was nonetheless seen before the final evaluation (see the caveat above).
- **Flash, partial.** In research the rule learned on level 2 also planned level 3 (66 actions, no no-ops). The final solver reused its level-1 goal on level 2 and still failed. In baseline+, its level-2 conclusion "dark = WALL" contradicts level 1, where it had walked on dark tiles, and it did not resolve the conflict.
- **27B, weak.** Its door maps are stored separately for each level, keyed `(R, C, lv)`. Its simulator invents synthetic levels 3–4 (`Q27/x_0001/solver/sim_game.py`). In evaluation the solver cleared level 2 by learning doors online (70 actions, 21 no-ops) and then stalled on level 3.

### Credit assignment

- **Max, strong in AVO and weak in baseline+.** In AVO it explained each level win from the cited transition events (34–35, 172–174, 376–379). In baseline+ it credited the level-1 push to "enter orange-hollow from below".
- **Flash, strong in baseline+ and partial in AVO.** In baseline+: "L1 won by pushing the ORANGE box onto the BLUE target". In AVO the solver attributes wins programmatically (`on_transition`: "goal … confirmed"), but Flash wrote no explanation of any win in its notes.
- **27B, weak.** Its AVO win theory is shifted by one step ("the next action completes the level"), which matches what the stale frame would show. On 8 Oct it never won in baseline+. The earlier 30 Sep–1 Oct runs credited an accidental level-1 win to the wrong cause ([failure analysis](qwen27b-modality-failure-analysis.md)).

### Verification and grounding (process row)

- **Max, strong.** It used two real self-checks. Check 1 scored 0/4 with a `KeyError: metadata` crash; Max fixed the envelope handling, and check 2 scored 4/4 (`MAX/x_0001/research/self_check/`). It also replayed every recorded transition and ran a hybrid real-pixel stream. One limit: the replay only covers transitions that were actually observed, so it could not catch the grey error.
- **Flash, weak.** It made no `solver_self_check_completed` events. It ended at the wall-clock limit in mid-edit ("Several concrete bugs identified. Let me rewrite the Controller…", `FL/x_0001/solver/agent_transcript.jsonl`) and tested against its own mock (`exp/mock.py`). It did check predictions against the real frame during research play.
- **27B, weak in the recent run.** It ran no real self-checks. Its local replay (`check.py`) "verified" the stale-frame model, and its simulator with synthetic levels reported a mock 4/4. It also ended mid-task at the time limit. The 30 Sep campaign used both real checks (0/4, then 1/4 with a crash; `AUD/historical-comparison.json`), so the model does invoke checks under other settings, and those checks did not produce a solve.

## What each model is good and less good at, in plain language

- **Max** is good at seeing the board, mapping the controls, building a predictive model and planning with it, and testing the final program for real. Its rules were still not fully correct: it never ran the one experiment that would have exposed the grey misunderstanding, and a plan that avoided those states won anyway. In direct play without code (baseline+) it misidentified the crate as a door and credited its first win to the wrong cause. Its baseline+ score of 1/4 matches Flash's.
- **Flash** is good at goal recognition, credit assignment and finding undo in direct play. In AVO research it found a nearly exact form of the real colour rule. It is less good at consolidating what it learned. It never wrote the rule down, delivered a solver built to re-learn everything, never tested that solver for real, and the solver looped on level 2. The audit does not allow us to say which of these caused the 1/4.
- **27B** is less good at the earliest stages of the pipeline. It reads the older frame and misreads undo (as a jump in baseline+, and through a previous-action direction model in AVO), and then builds elaborate hidden-state rules that agree with its own misreading. It does form the right goal hypothesis eventually, and it designs structured experiments, keeps notes and retracts claims. Its solvers loop on no-ops and were not tested for real in the recent run.

The clearest gradient is in **verification and grounding**: in the recent AVO runs, Max ran real checks and the other two did not. This is a recorded difference in behaviour, not a demonstrated cause. The 30 Sep 27B campaign also ran real checks and still did not solve the game.

## Candidate interventions (ranked)

The ranking weighs how directly the evidence implicates the capability, how cheap a test would be, and how well the intervention fits the proposal's "Second: locate the bottleneck" and "Third: build and ablate" sections. The test designs are sketches for planning. **None is scheduled**, and choosing whether to run them is Adam's decision.

Rough cost scale:

- Max is about $20 per run ($6 per M output tokens; most of the cost is input tokens).
- A Flash or 27B AVO run used 22–34M input and 0.5–0.7M output tokens. At $0.47 per M output, output costs under $0.40; the Alibaba input price is not recorded in the repository, so the estimate is roughly $1–10 per run.
- A Flash or 27B baseline+ run is roughly $1–2.

| # | Intervention | Capability | Cheapest test (model, game, harness, repeats) | Cost order |
|---|---|---|---|---|
| 1 | **Enforce a real self-check before finishing.** Reserve wall time and have the harness run `evaluate_solver` automatically if the model hasn't, then return the result for at least one repair turn. | Verification | 27B and Flash, Modality, AVO with the gate vs. current AVO, 3 repeats each (12 runs). Report final score, number of checks and crash rate. | ~$10–100 |
| 2 | **Observation API that returns only the latest frame**, or labels the frames explicitly as before/after. | Perception, which feeds action interpretation and rule induction | 27B, Modality, AVO with the latest frame only vs. current, 3 + 3 runs. Report whether delayed-action or hidden-variable theories appear, and the final score. (The offline parser patch alone scored 1/4, so this tests learning from clean observations, not a repair of the old solver.) | ~$10–60 |
| 3 | **Rival-hypothesis step with a discriminating probe.** For each surprising transition, list at least two explanations (including undo/reset and local vs. global causes), then choose the action that tells them apart. | Rule induction, action interpretation | 27B and Flash, Modality, baseline+ (100 actions) with the step vs. control, 3 + 3 each. Report correct undo identification, accuracy of the rule's predictions against native counterfactuals, and levels. The same probe would separate Max's grey-phase model from the real one. | ~$12–25 |
| 4 | **Supplied action meanings** (ACTION1–4 are directions, ACTION7 is undo; rules and goal stay hidden). | Action interpretation | 27B, Modality, baseline+, 3 repeats vs. the 8 Oct run plus 3 new controls. | ~$6–12 |
| 5 | **Supplied goal** (crate on target). | Goal recognition | 27B baseline+ ×3 (cheap). Max baseline+ ×3 tests whether Max's direct-play goal error limited it. | ~$6 for 27B; ~$60 for Max |
| 6 | **Consolidate research into the solver.** Require writing confirmed rules into `world_model.md` and building the solver on the validated research model. | Transfer, planning (compiling knowledge into the solver) | Flash, Modality, AVO with the instruction vs. current, 3 + 3. Whether online re-learning caused Flash's 1/4 is untested, so this run would test it. | ~$10–60 |
| 7 | **Supply the true mechanics, paired with the model's planner or a deterministic one** (diagnostic ceiling only). | Planning | 27B and Flash, AVO, 3 repeats. Any gap that remains points to planning or implementation rather than rule learning. | ~$10–60 |
| 8 | **A no-op watchdog plus an explicit policy for unknown moves.** Variant A treats unverified moves as blocked. Variant B leaves them unknown and probes them explicitly. | Planning | First an offline step at **$0**: rerun the saved 27B and Flash solvers with the watchdog in the offline simulator. If it changes the trajectories, then run Flash and 27B AVO ×3. Note the tension: Max's conservative but wrong model still won, Flash's own debugging found that treating untested objects as blockers stopped the box from reaching the marker, and the proposal's ledger says unknown moves must not be recorded as walls. | $0, then ~$10–60 |

**Top three:** (1) an enforced real self-check, (2) an observation that shows only the latest frame (for 27B), and (3) a rival-hypothesis step with a discriminating probe. Interventions 4 and 5 are the cheapest diagnostics: they would tell whether 27B's baseline+ failure starts in action interpretation or in goal recognition.

## Sources

`AUD/facts.json`, `AUD/native-verification.json`, `AUD/historical-comparison.json`; `INV/audit.json`, `INV/deep-checks.json`, `INV/offline-ablation.json`; run directories `20261013T150245-989f6c8b` (Max B+), `20261013T150241-d07d5558` (Flash B+), `20261008T112945-f705fa9a` (27B B+), and `MAX`, `FL`, `Q27` above (world models, notes, solvers, research `evidence.jsonl`, transcripts); `puzzlescript_interface/games/ps_modality-v1/script.txt` (used only for rule accuracy); [`qwen27b-modality-failure-analysis.md`](qwen27b-modality-failure-analysis.md).
