---
date: 2026-06-01
title: Goal-recognition model matrix on a curated 50-game pool
threads: [goal-recognition]
runs: []
commits: [4da037a, 5691ec8, 76e7731, 10842f6, 1a2c665, 2293673]
docs: [studies/goal_recognition/README.md, studies/goal_recognition/docs/goal-recognition-dropped-games.md, studies/goal_recognition/experiment/README.md]
reconstructed: true
---
## Did
- Curated the goal-recognition pool: 193 runnable games, 143 dropped, 50 kept (deterministic, readable, explicit objective).
- Collected evidence per game in two modes (one frame; three seeded random actions) × two inputs (text only; text plus first image).
- Ran a 3-shot collection (May 28) and an OpenRouter model matrix (May 31): Claude Opus 4.8, GPT-5.5, Kimi K2.6, DeepSeek V4 Pro.
- Published a static results viewer; Jun 4 moved side quests into `studies/` (goal recognition, LIVE framework, ReAct).
## Found
- The matrix artifact holds 1,153 predictions and 445 error records (`artifacts/2026-05-31T19-29-42-openrouter-matrix`). No accuracy summary is stored with it.
## Decided
- Keep source games on disk and filter the pool through `dataset/excluded_games.json`.
- Treat the 50-game experiment as pilot evidence unless the human sample grows (later note in `docs/notes/todo.md`).
## Next
- Return to rule learning with rendered frames.
