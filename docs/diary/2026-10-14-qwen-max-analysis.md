---
date: 2026-10-14
title: Qwen Max analysis, supervisor brief and NanoGPT provider
threads: [qwen-harness, workbench]
runs: []
commits: []
docs: [docs/research/qwen-modality-max-analysis-20261014.md, docs/research/qwen-modality-yoav-brief-20261014.md]
reconstructed: true
brief: true
---
## Did
- Analysed the Modality campaigns and the generated programs of Max, Flash and 27B.
- Wrote a meeting brief for Prof. Yoav Goldberg.
- Added NanoGPT as a third API provider (key staging, model catalog, launch UI, tests).
- Launched NanoGPT Modality runs overnight: 27B (thinking) and Flash, baseline+ and AVO.
## Found
- Max's solver reads the latest frame, identifies roles by sprite colour and runs BFS in a learned transition model; its world model is still wrong in 32 of 1,060 counterfactual directional cases.
- 27B's solver parses the older frame (`frame[0]`) and models invented delayed-action effects; its local simulator has synthetic later levels.
## Decided
- Present outcomes only; no claim yet about why Max succeeded.
## Next
- Audit every claim in the analysis before the meeting.
