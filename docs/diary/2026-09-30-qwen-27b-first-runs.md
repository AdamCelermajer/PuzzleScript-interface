---
date: 2026-09-30
title: Qwen 3.8-27B first runs and the OpenRouter harness ladder
threads: [qwen-harness, avo-campaigns, codex-direct-player]
runs: [output/workbench/20261001T000258-18c731e5, output/workbench/20261001T084700-f1d4ebb7, output/harness_smoke]
commits: []
docs: [docs/research/qwen-harness-direction.md, docs/architecture/workbench.md]
reconstructed: true
---
## Did
- Sep 30: routed OpenRouter models through Codex for the direct player; prompts now keep one current `world_model.md` with evidence and retractions.
- Ran Qwen 3.8-27B (OpenRouter) on Modality and IceCrates under AVO and baseline+.
- Probed note-tool use with and without an enforced JSON output schema (`output/diagnostics/qwen-notes-20260930T235031/`).
- Oct 1: added a harness ladder for AVO and the direct player: H0 `raw` (fenced bash blocks) and H1 `tools` (native shell/read/write/view_image); `--provider` pin; a lenient reply parser with a correction turn. Smoke runs in `output/harness_smoke/` (27B, 0/4 at 6 steps).
- Request-content and tool-name guards became explicit diagnostics instead of running on every normal run.
## Found
- Every 27B run cleared Modality level 1 and stalled on level 2; most were stopped by hand.
- Infra problems, not model behaviour: Docker down, isolation "private path", effort `max` rejected, Codex's own `get_goal` tool rejected by the guard, and invalid-action-JSON aborts in the old parser.
- Schema enforced: 0/2 note-tool calls; no schema: 2/2.
## Decided
- Invalid model output should trigger a correction turn, not end the run.
## Next
- Write up the research direction for the 27B.
