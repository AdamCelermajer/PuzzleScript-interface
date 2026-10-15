# Revamp status (2026-10-15, paused on usage limit)

Design: `revamp-contract.md`. Branch `workbench-revamp`.

## Done
- Phase 0 committed (`94086fe`).
- Benchmarks: `benchmark/games.json` (206 games, 24 mechanic + 12 property tags, 193 drafted),
  `scripts/build_game_metadata.py`, `scripts/draft_game_tags.py`, `workbench/benchmarks.py` router, tests pass.
- Diary: `docs/diary/` (32 entries, 31 reconstructed), `workbench/diary.py` router, AGENTS.md Diary section, tests pass.

## Interrupted mid-work (WIP, not verified)
- Harnesses: `harnesses/` has base, codex, claude_code, opencode, antigravity, chat (moved from
  `avo/client/openrouter_chat.py`), `docker/` image in progress. Missing: `bare.py`, `registry.py`,
  `launch.py`, `entry.py`, AVO/direct-player integration, deletion of the Codex isolation stack, tests, smoke.
- Workbench API: `workbench/runs.py`, `harness_catalog.py`, `avo_console.py`, `avo_replay_worker.cjs`,
  edits to `experiments.py`/`catalog.py`/`experiment_job.py`. Was splicing out the old resume
  handlers in `experiments.py` when stopped — check that file first.

## Next
1. Run `uv run python -m pytest -q tests avo/tests`; fix `workbench/experiments.py` and `avo/client/*` imports of the moved chat module.
2. Finish harnesses (contract §1–3), then register `benchmarks`, `diary`, `runs` routers in `workbench/app.py`.
3. Check whether containers can reach the workbench port (8010); block it if so (benchmark rules/summaries would leak).
4. Antigravity Docker login (`python -m harnesses.launch login antigravity`) needs Adam in a terminal.
5. Phase 3: React SPA.
