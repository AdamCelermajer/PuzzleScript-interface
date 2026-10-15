---
date: 2026-06-18
title: Verifier-gated rule induction and a direct OpenRouter client
threads: [rule-agent]
runs: []
commits: [f569b47, 5ae2696, 4b87004, 61647e8, 93fae29, 4f3ab27, ba2dfba, 233afa1, 8c5ecd3]
docs: [docs/notes/workbench-notes.md, docs/pseudocode/rule_learning.md]
reconstructed: true
---
## Did
- Jun 17: refactored goal planning; removed stale compatibility shims; replaced `litellm` with a direct OpenRouter client on the `openai` SDK; simplified rule artifacts and added a rule inspector.
- Jun 18: handled structured rule anchors in induction; gated induced rules through a deterministic verifier; updated the architecture pseudocode.
- Made Claude Opus 4.8 the default model.
## Found
- —
## Decided
- The LLM proposes a rule; only rules verified against the recorded timeline reach prediction and planning. Contradicted rules are deactivated and revised.
## Next
- Compare models and thinking modes on the same start state.
