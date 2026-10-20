---
title: What are Max, Flash and 27B good and bad at?
status: in-progress
order: 1
threads: [qwen-harness]
links:
  - "Capability scorecard notes | docs/research/capability-scorecard-modality-20261015.md"
  - "Modality claim audit | docs/research/qwen-modality-claim-audit-20261015.md"
  - "Board claim verification (19 Oct) | docs/research/board-claim-verification-20261019.md"
runs: [20261013T152559-avo-max-92c30e52, 20261013T173422-avo-flash-modality-recovery, 20261013T165330-avo-27b-modality]
artifact: docs/research/capability-scorecard-modality-20261015.json
---
## Question
Which of the proposal's seven capabilities do Qwen 3.8 Max, Flash and 27B show or lack on Modality?

## Current answer
Checked against the raw transcripts on 19 Oct. One run per model, so these are descriptions of what happened, not rates:
- **Max:** reads the latest frame, maps all five actions, plans with BFS and ran two real solver checks. Its rule is wrong in two ways: grey is modelled as a global phase toggle (too strict: 27 of 32 wrong predictions), and target cells are treated as always enterable (too permissive: 5 of 32). Neither error occurred on its 265-action path.
- **Flash:** perceives well and names the goal. Its research planner held the exact player-movement rule and won levels 2 and 3 with it, but it never wrote the rule into its notes and never ran a real check of the delivered solver. The delivered solver re-learned the movement rule online by step 80 and still looped on level 2. Why it looped is not established.
- **27B:** reads the older of the two frames and models actions as depending on the previous action. It kept notes, ran structured probes and retracted claims, but its rules fit its own misreading. Its solver still beat Flash's (2/4 vs 1/4).

## Evidence
- Final fresh-solver results on Modality: Max 4/4 (265 actions), Flash 1/4 (1,500), 27B 2/4 (1,500). Research progress: Max 3/4, Flash 3/4, 27B 1/4. All replayed in the native engine with zero mismatches.
- Real self-checks: Max 2 (first crashed on a `KeyError`, second 4/4), Flash 0, 27B 0.
- Flash's research planner allowed any move except directly between white and dark. That is the game's player-movement rule exactly; it does not encode the push-compatibility rule. Flash never wrote it down; its final solver learned the same exclusion online and still failed.
- In baseline+, Max took the crate for a door and tested exits (1/4). 27B took undo for a "jump", pressed it 13 times, pushed the crate into a corner at t23 and concluded there was no reset (0/4). Whether the goal misreading caused Max's 1/4 is untested.
- Max never tried moving from grey back onto the colour it came from (0 of 8 research and 0 of 15 evaluation departures from grey). That test would have exposed its grey rule.

## Next
- Decide which of these descriptions to present as findings and which as hypotheses.
- One run per model, so there is no variance estimate; see the verification note for the single repeat that would help most.
