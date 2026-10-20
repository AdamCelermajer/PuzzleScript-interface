---
title: Can Flash solve these games, or only Max?
status: in-progress
order: 3
threads: [qwen-harness]
links:
  - "Capability scorecard notes | docs/research/capability-scorecard-modality-20261015.md"
  - "Modality claim audit | docs/research/qwen-modality-claim-audit-20261015.md"
  - "Board claim verification (19 Oct) | docs/research/board-claim-verification-20261019.md"
runs: [20261013T152559-avo-max-92c30e52, 20261013T173422-avo-flash-modality-recovery]
---
## Question
Can Flash solve these games, or only Max? Flash is much cheaper to run.

## Current answer
Checked against the raw transcripts on 19 Oct. One run each, so this is not settled:
- Flash reached 3/4 levels during research, but its delivered solver scored 1/4. Max's delivered solver scored 4/4.
- Flash's research planner held the exact player-movement rule and won research levels 2 and 3 with it. It never wrote the rule down and never ran a real check of the solver. The solver re-learned the same rule online within 80 actions and still looped on level 2, so a missing rule is not the demonstrated cause. The cause of the 1/4 is open.
- Flash's cheaper NanoGPT direct-play run on 15 Oct reached 2/4 (296 actions, stopped by hand), so its single 1/4 AVO result is not a ceiling.
- No repeat exists. The old Codex-to-OpenRouter route is gone, so any new Flash or Max run is also a harness change.

## Evidence
- Flash: 3/4 levels during research (wins at research steps 49, 85, 151 of 160), 1/4 for the final solver, 0 real self-checks. The final solver spent 1,490 actions on level 2 (740 down, 736 up).
- Max: 4/4 for the final solver, 2 real self-checks. The second check and the final evaluation are the same 265 actions.
- Flash's `exp/plan.py` forbade only moves directly between white and dark, which is the game's player-movement rule. Its notes and world model never recorded the rule, and its final solver relearns rules online and never plans with undo.
- Offline, fixing the solver's visit key or forcing a static goal left it at 1/4 (simulator results, not reruns).
- Harness note:
  - All three Modality AVO runs (Max, Flash, 27B) used the Codex harness routed to OpenRouter with Alibaba as provider. That route has since been removed, and Codex is now OpenAI-only.
  - No Qwen run on the new OpenCode or bare harness exists yet; the 15 Oct NanoGPT runs still used the Codex harness. Results from different harnesses will not be directly comparable.

## Next
- Decide whether one repeat Flash AVO run on Modality (current harness) is worth its cost before Thursday; it is the single run that could overturn this card.
