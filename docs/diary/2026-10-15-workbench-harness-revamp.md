---
date: 2026-10-15
title: Workbench and harness revamp
threads: [harness-revamp, workbench, benchmark-curation]
runs: [harness-smoke-*]
commits: [94086fe, f5ead4f, 951ced8, 9bfd741]
docs: [docs/architecture/revamp-contract.md, docs/architecture/revamp-status.md, harnesses/README.md, docs/diary/README.md]
reconstructed: false
brief: true
---
## Did
- Committed the in-flight work as phase 0 (`94086fe`): NanoGPT provider, `image` gateway tool, `max_wall_seconds=0` = unlimited.
- Built `harnesses/`: codex, claude-code, opencode, antigravity and `bare` behind one session interface, one Docker image, one launcher (`python -m harnesses.launch`) for baseline, baseline-plus and campaign. Deleted the Codex sandbox, request proxy and the old OpenRouter H0/H1 loops.
- Unified the workbench API (`/runs` matrix launch, `/runs/resume`, `/harnesses`) and moved the Vite-only routes into FastAPI.
- Replaced the multi-page site with one React app (`website/app/`) on port 5173: Runs, Launch, Run detail, Compare, Benchmarks, Diary, Tools.
- Built `benchmark/games.json` (206 games, 24 mechanic + 12 property tags, drafted for 193 games by Claude).
- Started this diary with 31 reconstructed entries.
## Found
- All four CLIs run headless with JSON events and resumable sessions; Qwen 3.8 27B made a correct tool call through OpenCode on the first try.
- Smoke in Docker passed for codex, claude-code, opencode and bare; a 3-step baseline-plus run (claude-code haiku, modality) and a tiny opencode campaign completed.
- Docker Desktop containers can reach every host port, even ones bound to 127.0.0.1; the server sees them as 127.0.0.1.
## Decided
- Simplicity over security: plain containers, no firewall, workbench open to any hostname (Tailscale laptop).
- `bare` (ex-H1) stays as the minimal research harness; H0 dropped. OpenCode replaces the custom OpenRouter loop for Qwen runs, so later Qwen results come from a different harness.
- Never touch the host OpenCode install (T3 Code depends on it).
## Next
- Antigravity Docker login, then its smoke run.
- Review the drafted benchmark tags; assign tiers to the 174 untiered games.
- Re-run the Qwen baselines through OpenCode and bare to compare with the old harness results.
