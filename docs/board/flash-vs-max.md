---
title: Can Flash solve these games, or only Max?
status: in-progress
order: 3
threads: [qwen-harness]
links:
  - "Capability scorecard notes | docs/research/capability-scorecard-modality-20261015.md"
  - "Modality claim audit | docs/research/qwen-modality-claim-audit-20261015.md"
runs: [20261013T152559-avo-max-92c30e52, 20261013T173422-avo-flash-modality-recovery]
---
## Question
Can Flash solve these games, or only Max? Flash is much cheaper to run.

## Current answer
From existing evidence only:
- Flash reached 3/4 levels during research, but its final solver scored 1/4. Max's final solver scored 4/4.
- Flash's research planner nearly found the true colour rule. So the gap looks like a failure to carry what it found into the final solver and to check it, more than a lack of ability.
- This is one run each, and no new runs are scheduled.

## Evidence
- Flash: 3/4 levels during research, 1/4 for the final solver, 0 self-checks.
- Max: 4/4 for the final solver, 2 self-checks.
- Flash's `exp/plan.py` forbade only moves directly between white and dark, which is the game's rule. Its notes and world model never recorded the rule, and its final solver relearns rules online without undo.
- Harness note:
  - All three Modality runs (Max, Flash, 27B) used the old Codex harness routed to OpenRouter. That route has since been removed, and Codex is now OpenAI-only.
  - Later Qwen runs use OpenCode or bare, so results from the two harnesses are not directly comparable.

## Next
- Decide whether matched Flash and Max runs on the new harness are worth scheduling.
