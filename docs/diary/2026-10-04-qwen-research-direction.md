---
date: 2026-10-04
title: New main thread, why Qwen 3.8-27B fails
threads: [qwen-harness, proposal]
runs: []
commits: []
docs: [docs/research/qwen-harness-direction.md]
reconstructed: true
brief: true
---
## Did
- Oct 4: wrote `qwen-harness-direction.md` from Adam's notes: three candidate explanations (harness, size, pretraining) and a five-step plan.
- Oct 5: corrected the run reading. Most "cancelled" 27B runs were stopped by hand to save money; the connection-reset error is a side effect of the stop.
- Added per-run cost and provider notes from `codex_session.jsonl` usage.
## Found
- Every 27B run cleared Modality level 1 and stalled on level 2, including a max-effort run of 124 actions.
- Input tokens dominate cost: the 124-action run used about 10.4M input tokens (83% cached) and 0.11M output.
- With a JSON output schema enforced, 27B made 0/2 note-tool calls; without it, 2/2 (`output/diagnostics/qwen-notes-20260930T235031/`).
## Decided
- Main goal: make Qwen 3.8-27B solve the games through a better harness, after first understanding why it fails.
- Plan: failure taxonomy → Qwen family size sweep with controls → pretraining probes → harness ablations → trace comparison.
- The M.Sc proposal follows the same correlational → interventional structure.
## Next
- Read the 27B failure reasons on Modality level 2; rerun with clean transport.
