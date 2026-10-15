---
date: 2026-10-15
title: Workbench and harness revamp
threads: [harness-revamp, workbench, benchmark-curation]
runs: []
commits: [94086fe]
docs: [docs/architecture/revamp-contract.md, docs/diary/README.md]
reconstructed: false
---
## Did
- Committed the in-flight work as phase 0 (`94086fe`): NanoGPT provider, `image` gateway tool, `max_wall_seconds=0` = unlimited.
- Wrote the revamp contract (`docs/architecture/revamp-contract.md`) that the parallel revamp builds against.
- Installed Antigravity CLI 1.3.5 and logged it in; set up a long-lived Claude Code token (`CLAUDE_CODE_OAUTH_TOKEN`).
- Started this research diary: entries in `docs/diary/`, `workbench/diary.py` API, backfill from git history and research docs.
## Found
- All four CLIs (codex, claude-code, opencode, antigravity) ran headless on Windows, made a shell tool call and returned session ids.
- OpenCode needs models unknown to models.dev (e.g. `qwen/qwen3.8-27b`) declared in `opencode.json`.
## Decided
- Four CLI harnesses (codex, claude-code, opencode, antigravity) plus an in-process `bare` loop, all resumable, permission prompts off, web tools off, same system prompt, one effort scale.
- Plain Docker isolation: one container per run, `--cap-drop ALL`, no Codex sandbox, no request proxy.
- One run spec (`run_spec.json`) and one launcher (`harnesses.launch`) for baseline, baseline-plus and campaign modes; one normalized `agent_events.jsonl`.
- Workbench becomes a React SPA that talks only to FastAPI.
- Games get metadata and benchmark tags in `benchmark/games.json`; solve rates are computed live from the run catalog.
- Never touch the host OpenCode install (T3 Code depends on it).
- Keep this diary: one terse entry per substantial session, with a supervisor export.
## Next
- Land the harness launcher, SPA, benchmark tags and diary routes, then smoke-test each harness end to end.
- Check that old run folders still appear in the catalog next to `run_spec.json` runs.
