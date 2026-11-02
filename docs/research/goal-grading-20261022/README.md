# Goal-recognition grading (22 Oct 2026)

Every answer in the goal-recognition study (50 games; 112 human answers from 38 people, 699 model answers) graded
correct, partial or wrong against the game's real goal, read from its `script.txt` (WINCONDITIONS and level design).

- `graded.json`: `rows` (game, answer id, source, condition, verdict) and `goals` (the real goal per game).
- `goal-recognition.png`, drawn by `make_figure.py`: first-frame accuracy per answerer, and one frame vs three random
  actions first (with the first image) per model.

Answers come from the study's results viewer data (`studies/goal_recognition/`). Grading: Claude subagents, one game
at a time, with the script and all answers for that game.
