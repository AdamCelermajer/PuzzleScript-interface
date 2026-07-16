# Project Notes

## Ready

- Natural rule = readable hypothesis. Logical rule = executable version used by the planner.
- Compiler asks the LLM for logical JSON. Verifier checks it against real transitions. Failed rules never reach planning.
- Each transition proposes at most one temporary NL candidate; it appears as a rule only after logical verification, and equivalent verified rules reuse one NL entry.
- Prompts are editable in the Workbench and snapshotted with each run. Raw JSON responses are saved for diagnosis.
- If a rule predicts incorrectly, its NL and logical versions become inactive. Revision replaces or splits them, then verifies the replacement against old and new evidence.
- Example split: moving into an empty cell versus moving in the same direction while pushing a crate.

## Demo

1. Check OpenRouter and the 12-step local settings.
2. Start Fresh and show the frame, action, goal, plan, legend, and rules advancing.
3. Open rule attempts and explain compilation and verification.
4. Use Replay to show frames, predictions, and rules appearing over time.
5. Open Architecture and follow the pseudocode flow.

Fallback: use the saved rehearsal artifacts if the live provider is unavailable.

## Status

- Full Python and Node suite passes: 152 passed, 2 skipped.
- Website tests: 10 passed.
- Website build and desktop/mobile checks pass.
- Full level completion is useful, but learning progress is enough for the demo.
- Terminal and Tkinter still exist only as fallback code.

## Next Week

- Analyze real rule_attempts.jsonl failures and improve the prompts.
- Measure hypothesis-to-verification success.
- Test revision and rule splitting on more mechanics.
- Compare OpenRouter models, cost, and reasoning effort.
- Run more PuzzleScript games and official ARC tasks.
- Revisit rule families or merging later.

## Scratch

-
