---
date: 2026-11-04
title: Partial Astra rule-learning audit and grader provenance
threads: [qwen-harness]
runs: []
commits: []
docs: [docs/research/rule-learning-audit-20261104/REPORT.md]
reconstructed: false
---
## Did
- Inventoried 208 checkpoints / 1,554 labels; independently graded only B/000, D/000 and E/000 (22 labels) in a separate audit directory.
- Inspected current game-rule source and extracted model metadata for 29 historical grader segments.
## Found
- All 29 segment logs record claude-opus-5-5; no Haiku in those records.
- Full regrade remains incomplete: 205 checkpoints / 1,532 labels unreviewed. No original-label comparison performed.
## Decided
- Preserve originals and curves; keep identity key and prior raw grades unread. Do not present partial labels as a complete audit.
## Next
- Complete sequential grading, freeze labels, then compare and classify disagreements with evidence.
