# Revamp status (2026-10-15)

Design: `revamp-contract.md`. Branch `workbench-revamp`.

## Done
- Harnesses (`harnesses/`): codex, claude-code, opencode, bare verified in Docker
  (smoke + one baseline-plus run + one tiny campaign). One image `puzzlescript-agents:local`
  (`docker build -t puzzlescript-agents:local harnesses/docker`). Plain container, no
  firewall: containers can reach host services, accepted for simplicity.
- Workbench API: `/harnesses`, `/runs` (matrix), `/runs/resume`, normalized catalog,
  Vite dev routes ported to FastAPI, benchmarks/diary/runs routers registered.
- SPA (`website/app/`): Runs, Launch, Run detail, Compare, Benchmarks (+ Play, tag review),
  Diary (+ export), Tools (Notes, Paper investigation, BFS). Served on 5173 by
  `scripts/start-workbench.ps1`; `allowedHosts: true`.
- Benchmarks: `benchmark/games.json`, 193 drafted tag sets awaiting review.
- Diary: `docs/diary/`.
- Board: `/board` in the SPA, `workbench/board.py`, cards in `docs/board/` (Present mode, PDF export).
- Antigravity: Docker login done, smoke passed.

## Open
- Antigravity: confirm the web-blocking hook fires.
- OpenCode provider pin and `--variant` values unverified.
- Old `website/` pages (and `website/vite.config.js`, `game-library-server.mjs`) are unused;
  delete when no longer wanted.
- `aiohttp` unused in the lockfile; `openai-codex` still used by `workbench/paper_investigation.py`.
- Tags: review drafts in Benchmarks → filter "draft".
- Note the harness change (OpenCode / bare replace the old OpenRouter H0/H1 loops) in the Qwen research docs.
