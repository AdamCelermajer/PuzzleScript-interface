---
date: 2026-10-15
title: Capability scorecard, real-time direction, and the Board
threads: [qwen-harness, realtime-controllers, proposal, workbench]
runs: [20261013T152559-avo-max-92c30e52, 20261013T173422-avo-flash-modality-recovery, 20261013T165330-avo-27b-modality]
commits: []
docs: [docs/research/capability-scorecard-modality-20261015.md, docs/research/realtime-llm-controllers-direction.md, docs/board/]
reconstructed: false
---
## Did
- Scored Max, Flash and 27B on the proposal's seven capabilities, plus verification, using only existing Modality evidence. Produced a Markdown report and JSON.
- Mapped prior work on real-time LLM agents with fast controllers and Jev-style decision models (about 80 entries). Compared 11 environments and sketched a framework with a first experiment.
- Added a Board to the workbench (`/board`, `workbench/board.py`, cards in `docs/board/`) with a Present mode and PDF export, for the 22 Oct meeting.

## Found
- Max: 2 real self-checks, wrong but conservative grey rule. It never tried moving from grey back onto the original colour, the test that would have exposed the rule.
- Flash's research planner forbade only moves directly between white and dark, which is nearly the true rule. It never recorded the rule, and its final solver (1/4) didn't use it.
- In baseline+, Max took the crate for a door, and 27B took undo for a "jump" and concluded there was no reset.
- All three Modality AVO runs used the old Codex harness routed to OpenRouter.
- Nearest real-time work: Code to Control (arXiv 2609.38733) writes controllers offline, with no LLM at runtime and no online repair. Nothing found learns unknown rules and repairs controllers while acting.
- Our runtime only advances after an input, so real-time PuzzleScript first needs a no-op tick action and a clock driver.

## Decided
- Codex stays OpenAI-only. Results from the old Codex/OpenRouter Qwen runs are reported with a harness note rather than re-run.
- No new runs for now; interventions and the first real-time experiment remain designs.

## Next
- Review the scorecard ratings and the real-time shortlist (PuzzleScript real-time, Atari subset, RoboCup 2D for Gal).
- Present from the Board on Thursday 22 Oct.
