---
title: What would the real-time framework look like?
status: in-progress
order: 6
threads: [realtime-controllers]
links:
  - "Real-time direction notes | docs/research/realtime-llm-controllers-direction.md"
runs: []
artifact: docs/research/realtime-llm-controllers-direction.json
---
## Question
What components would a framework for a slow LLM steering fast controllers need, and what is the first experiment?

## Current answer
Draft sketch:
- **Slow coding agent** (any existing harness): learns the rules and maintains a library of tested Python controllers and typed decision questions.
- **Fast arbiter:** runs the controllers every tick under a hard deadline, with a fallback action.
- **Jev or a self-hosted JEV model:** answers the mid-rate choices.
- **Monitor:** wakes the agent on errors, missed deadlines, prediction mismatches, low confidence, novelty or stalls.

## Evidence
- First experiment (about 2 weeks, design only):
  - compares a paused LLM, a real-time LLM every step, code controllers only, and code plus one Jev question;
  - at 8×, 4× and 1× slowdown;
  - on 3–4 PuzzleScript games.
- JEV-27B-VL is built on Qwen 3.8-27B, the model in the main thread.
- This extends AVO from one offline `solver.py` to a controller library that is repaired while the game runs.

## Next
- Agree on the components and the first experiment.
