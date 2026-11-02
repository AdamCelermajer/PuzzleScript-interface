---
date: 2026-10-31
title: Shared PuzzleScript backend in Docker
threads: [arc-environment]
runs: []
commits: []
docs: [docs/architecture/docker-backend.md]
reconstructed: false
brief: true
---
## Did
- Added a two-service Compose backend and explicit start/stop/status/log commands.
- Kept the workbench local; its launcher now uses Docker, with a local debugging option.
## Found
- Agent runs already use Docker and connect through host.docker.internal:8000.
- Game sessions and API scorecards are in-memory; runtime history is on disk.
- Both host and agent-image checks passed against 193 games: reset, action, snapshot restore and close.
- Explicit stop/start preserved the existing game-history file.
## Decided
- Preserve existing game/history paths and campaign networking; no automatic container restart.
- Keep credentials and results outside backend images using narrow build contexts.
## Next
- Use the Docker backend for subsequent local PuzzleScript campaigns.
