---
date: 2026-10-11
title: Workbench speed-up and commit of pending harness work
threads: [workbench, avo-campaigns]
runs: []
commits: [bcd2bd8]
docs: [docs/architecture/workbench.md, docs/research/avo-framework.md, docs/research/three-game-mechanics-demo.md]
reconstructed: true
---
## Did
- The run catalog carries compact per-run result inputs, so result pages no longer fetch every run archive.
- `/catalog` serves the last snapshot at once and rebuilds once in the background (gzip, `scandir`).
- AVO console polling no longer aborts slow requests or rewrites an unchanged DOM.
- Committed pending work: OpenRouter raw/tools harnesses for AVO and the direct player, benchmark library with manual play and notebook, active-runs home page, mechanics page, research notes and the proposal draft.
## Found
- —
## Decided
- Local scratch (`tmp/`), generated TextWorld games (`tw_games/`) and a stray `%SystemDrive%` folder are gitignored.
## Next
- —
