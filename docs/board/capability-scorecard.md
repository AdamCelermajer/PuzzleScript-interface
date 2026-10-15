---
title: What are Max, Flash and 27B good and bad at?
status: in-progress
order: 1
threads: [qwen-harness]
links:
  - "Capability scorecard notes | docs/research/capability-scorecard-modality-20261015.md"
  - "Modality claim audit | docs/research/qwen-modality-claim-audit-20261015.md"
runs: [20261013T152559-avo-max-92c30e52, 20261013T173422-avo-flash-modality-recovery, 20261013T165330-avo-27b-modality]
artifact: docs/research/capability-scorecard-modality-20261015.json
---
## Question
Which of the proposal's seven capabilities do Qwen 3.8 Max, Flash and 27B show or lack on Modality?

## Current answer
First draft, from existing evidence and one run per model:
- **Max:** strong on perception, action interpretation, planning and verification. Only partial on rule induction: it solved the game with a wrong but conservative rule.
- **Flash:** perceives well and recognises the goal, but its final solver plans weakly and it never checks its own model.
- **27B:** weak almost everywhere. It reads the old frame and misreads actions.

## Evidence
- Final fresh-solver results on Modality: Max 4/4, Flash 1/4, 27B 2/4.
- Self-checks against the real game: Max 2, Flash 0, 27B 0.
- Flash's research planner allowed any move except directly between white and dark. That is nearly the true rule, but Flash never wrote it down and its final solver didn't use it.
- In baseline+, Max took the crate for a door. 27B took undo for a "jump" and concluded there was no reset.
- Max never tried moving from grey back onto the original colour. That test would have exposed its wrong rule.

## Next
- Review each rating and the evidence behind it.
- One run per model, so there is no variance estimate.
