---
date: 2026-01-07
title: PuzzleScript game server with a REST API
threads: [arc-environment]
runs: []
commits: [44bee81, 164e0a8, 633de98, f38f622, 304c8c6, 46c3c3c, 585a0ec]
docs: [README.md]
reconstructed: true
---
## Did
- Wrapped the `puzzlescript` npm engine in a Node.js Express server with game init, action and observe endpoints.
- Fixed server-side rendering for compound tiles, message levels and restarts; added `game_history.jsonl` session logging.
- Restructured the repo into `src/` and `games/`; games load by name; responses carry a structured `boardJSON`.
- Added a thin interactive CLI client (arrow commands, JSON board inspection) and a README.
## Found
- Game sources needed line-ending normalisation (`\r`) before the engine would parse them on Windows.
## Decided
- The engine stays in Node (only an npm package exists); everything else talks to it over HTTP.
## Next
- Put an LLM in the loop as the player.
