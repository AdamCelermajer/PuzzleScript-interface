---
title: Which environment or challenge for the real-time direction?
status: in-progress
order: 5
threads: [realtime-controllers]
links:
  - "Real-time direction notes | docs/research/realtime-llm-controllers-direction.md"
runs: []
artifact: docs/research/realtime-llm-controllers-direction.json
---
## Question
Which environment or challenge should the real-time work use, including 2–3 robotics options for Gal Kaminka?

## Current answer
Eleven options compared. The shortlist has one per audience:
1. **Continuity:** the real-time PuzzleScript games already in our catalog.
2. **ML community:** a small Atari subset, where the nearest work reports its results.
3. **Gal:** RoboCup Soccer Simulation 2D. VMAS swarms and lifelong multi-robot path finding are the robotics alternatives.

## Evidence
- 19 catalog games are excluded as `realtime`, 7 of them for that reason only.
- Our runtime only advances after an input. The npm engine's `tick()` already handles the timer, so we first need a no-op TICK action and a clock driver.
- RoboCup 2D runs in 100 ms cycles with decentralised players, and no LLM work on it was found.
- Not yet checked: which of the real-time games actually create time pressure.

## Next
- Pick one environment per audience for the presentation.
