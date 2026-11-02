---
date: 2026-10-22
title: Goal-recognition answers graded against the game scripts
threads: [goal-recognition, proposal]
runs: []
commits: []
docs: [docs/research/goal-grading-20261022/goal-recognition.png, docs/research/goal-grading-20261022/README.md, docs/research/goal-grading-20261022/graded.json]
reconstructed: false
---
## Did
- Graded all 811 answers of the 50-game study (112 human answers from 38 people, 699 model answers) correct, partial or wrong against each game's real goal from its `script.txt`.
- Drew the summary figure and put the numbers into the proposal's goal table.
## Found
- From the first frame with the image, correct / correct or partial: humans 20% / 46%, GPT-5.5 38% / 64%, Kimi K2.6 34% / 64%, Claude Opus 4.8 24% / 64%. DeepSeek V4 Pro takes no image: 18% / 46% from the grid alone (`docs/research/goal-grading-20261022/graded.json`).
- Three random actions before answering made every model worse: GPT-5.5 38 to 30%, Kimi K2.6 34 to 18%, Claude Opus 4.8 24 to 12%.
- The models name the exact goal more often than the human first-frame answers; counting partial answers too, it is 46% for humans against 64% for the three image models.
## Decided
- The proposal reports the one-frame-plus-image condition, with DeepSeek's grid-only number in the caption.
## Next
- Hand-check a sample of the grades before citing them as final.
