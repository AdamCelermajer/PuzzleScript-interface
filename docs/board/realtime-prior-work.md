---
title: "Real-time LLM + fast controllers (Jev): what has been done?"
status: in-progress
order: 4
threads: [realtime-controllers]
links:
  - "Real-time direction notes | docs/research/realtime-llm-controllers-direction.md"
runs: []
artifact: docs/research/realtime-llm-controllers-direction.json
---
## Question
What prior work combines a slow LLM with fast low-level controllers in real-time settings?

## Current answer
First draft written, with about 80 entries.

Existing work keeps the LLM out of the fast loop in one of four ways:
- pausing the game;
- choosing turn-based games;
- generating code or macros offline;
- using trained fast policies that receive occasional language subgoals.

Nothing found does all four of these together:
1. learns unknown rules;
2. compiles them into a controller library plus typed decision calls;
3. repairs controllers online while acting;
4. reports the latency–quality–cost trade-off.

## Evidence
- The nearest neighbour is Code to Control (arXiv 2609.38733, 30 Sep 2026). It writes reactive controllers offline, with no LLM at runtime and no online repair.
- Jev-style handing of uncertain decisions to an LLM has been validated only for text annotation (Ibrahim & Zaki, arXiv 2609.24574).
- Typed decision models follow an option's name over its definition (arXiv 2609.26758), so question wording must be tested.
- Jev's speed and cost figures are self-reported, and no model size is published.

## Next
- Re-check the gap before the meeting: Code to Control is recent and follow-ups may appear.
