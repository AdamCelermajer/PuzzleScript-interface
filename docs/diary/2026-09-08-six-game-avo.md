---
date: 2026-09-08
title: Six-game AVO campaigns, Astra outer and Luna inner
threads: [avo-campaigns]
runs: [output/opencode-modality-muse-20260910-02]
commits: []
docs: [docs/research/three-game-mechanics-demo.md]
reconstructed: true
brief: true
---
## Did
- Docker preflights passed; a six-game smoke passed 6/6 (`output/avo-docker-six-smoke`).
- Ran six games (Modality, Purple, Knightoban, Magnetic, Atlas Shrank, Enqueue): Astra low outer, Luna high inner, 300 research steps, 1,500 solver steps.
- Continued Knightoban, Atlas and Enqueue toward 10 evaluations (`output/avo-three-continue-x10-20260908*`).
- Sep 9: backfilled world-model reports for the six best candidates; visible-texture audit passed 188/193 games. Sep 10: OpenCode harness trial (muse-spark) on Modality.
## Found
- Attempts r1–r6 aborted on isolation errors (unapproved tools, private path reaching model context).
- r7 (stopped by the watchdog at the 03:50 deadline): Modality 4/4, Purple 4/4, Magnetic 4/4; Knightoban 0/6, Atlas 2/12, Enqueue 2/14 (`output/avo-six-live-20260908-r7/final-summary.md`).
- Continuation r3: Knightoban solved 6/6 after 8 evaluations; Enqueue stayed at 2/14 amid evaluation-service errors.
- OpenCode muse-spark: best 3/4 on Modality after 9 evaluations.
## Decided
- —
## Next
- Consolidate the workflows and the launch path.
