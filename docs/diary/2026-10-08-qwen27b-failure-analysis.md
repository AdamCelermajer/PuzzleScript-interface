---
date: 2026-10-08
title: Why 27B stalls on Modality level 2, and the first proposal draft
threads: [qwen-harness, proposal]
runs: []
commits: []
docs: [docs/research/qwen27b-modality-failure-analysis.md, docs/research/qwen-harness-direction.md, docs/proposal/README.md]
reconstructed: true
---
## Did
- Compared 27B traces with GPT-5.5 on Modality from existing logs (no new model calls).
- Reran 27B baseline+ pinned to DeepInfra (IceCrates, Knightoban, Modality) and on Alibaba for Modality.
- Wrote the first M.Sc proposal draft (`docs/proposal/main.tex`) for Overleaf.
## Found
- 27B never identifies undo (ACTION7) or crate pushing; it invents jump/trampoline/decoy theories and credits its level-1 win to the wrong cause. GPT-5.5 found undo and pushing within minutes.
- The failure is hypothesis formation and revision, not protocol or perception.
- DeepInfra caps requests at 30 images, so pinned runs ended at 30 actions; older unpinned runs (124 actions) were not served by DeepInfra.
- Alibaba rerun: Modality 0/4 at 100 steps; another rerun: IceCrates 3/6 and Knightoban 0/6 at 120 steps.
- The earlier `get_goal` abort came from Codex offering its own tools, not from the model.
## Decided
- Use Alibaba (first-party, no image cap) for Qwen precision reruns.
## Next
- Compare across the Qwen family (Flash, Max) under the same harness.
