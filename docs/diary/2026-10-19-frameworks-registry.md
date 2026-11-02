---
date: 2026-10-19
title: Frameworks next to harnesses; Harness² read
threads: [harness-revamp, workbench, qwen-harness]
runs: []
commits: []
docs: [frameworks/README.md]
reconstructed: false
brief: true
---
## Did
- Read Google Research Harness² (arXiv 2610.14224, github.com/google-research/harness2) and ran its offline demo in Docker: a fixed propose (INV + DOM) → probe → compose → reflect pipeline per task, score-blind, editing an 8-part harness folder (AGENTS.md, guardrails, memory, tool guidance, skills, subagents, scripts, plugins) on top of OpenCode or Codex, with a per-domain library across tasks.
- Added the framework axis next to the harness axis: `frameworks/base.py` (Framework, Option) and `frameworks/registry.py`; moved `avo/` → `frameworks/avo/` and `studies/codex_agent/` → `frameworks/baseline/`; baseline and baseline+ became one framework with a `notes` option.
- Launcher flags come from the registry (`--framework`, per-framework options); run_spec schema `run-spec-v2`; workbench API `GET /frameworks`, runs requests take `frameworks: [{id, options}]`; Launch page builds framework cards from the registry. Old outputs and v1 specs still read.
## Found
- Harness² paper: the unmodified CLI alone moves base scores by up to 8.3 points (Gemini 3.5 Flash on LAB: OpenCode 79.9 vs Codex 71.6), more than one Harness² step adds there; the order flips by benchmark.
- Harness² at k=1 adopts the composed harness without comparing it to the base run, and every task restarts from the base harness; only the library carries over.
- `tests/website/static-site.test.js` fails 3 tests on HEAD too (old static site), unrelated.
## Decided
- "Framework" names the method axis, "harness" the CLI axis. Outputs from before the move stay in `avo/output/` and `studies/codex_agent/output/`; new CLI runs go to `output/<framework>/`.
- Harness² comes next as a third framework, not as a dependency of AVO.
## Next
- Restart the workbench (`npm run workbench`) so the API loads the framework code.
- Harness² framework: game CLI the executor drives itself, PuzzleScript BenchmarkAdapter over `frameworks/avo/run_once.execute_player_run`, improver via claude-code or OpenCode, k=1 pilot on Modality with Qwen 3.8-27B.
