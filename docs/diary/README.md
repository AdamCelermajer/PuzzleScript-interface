# Research diary

Short, dated entries recording what was done, what was found, what was decided
and what comes next. They replace the usual "big PowerPoint" timeline and are
written so an AI assistant can maintain them. The workbench renders them
(`GET /api/workbench/diary`), links each entry to the runs started that day, and
exports a supervisor handout (`GET /api/workbench/diary/export?format=md|html`).

## Entry format

One file per entry: `docs/diary/YYYY-MM-DD-<slug>.md` (slug: lowercase letters,
digits and hyphens). The format is fixed by
`docs/architecture/revamp-contract.md` section 6.

```markdown
---
date: 2026-10-15
title: Workbench and harness revamp
threads: [harness-revamp]
runs: []          # run ids / output paths; runs started on `date` are linked automatically
commits: [94086fe]
docs: [docs/architecture/revamp-contract.md]
reconstructed: false
---
## Did
- ...
## Found
- ...
## Decided
- ...
## Next
- ...
```

Rules:

- The body has exactly the four sections `## Did`, `## Found`, `## Decided`,
  `## Next`, in that order, and nothing before `## Did`. A section with nothing
  to say contains `- —`.
- Bullets are terse facts. The whole entry fits on one screen.
- The first thread is the entry's primary thread (the export groups by it).
  Every thread must be in the registry below; add a row when starting a new one.
- `commits` are short SHAs; `docs` and `runs` are repo-relative paths. A `runs`
  item links that run and every run below it; a trailing `*` links every run id
  with that prefix (e.g. `output/workbench/20260923T*`).
- `reconstructed: true` marks entries written after the fact from git history,
  documents and run folders. Live entries are `reconstructed: false`.
- Claim only what the sources show. Cite numbers with their source document or run.
- Runs stopped from the workbench are usually stopped by hand to save money.
  Write "stopped", not "failed", unless an artifact shows a real error.
- Quiet periods are merged into one entry (for example a weekly entry).

## Threads

| Thread | Description | Status |
|---|---|---|
| `arc-environment` | PuzzleScript Node runtime and the ARC-AGI-3-compatible Python service | stable |
| `rule-agent` | Historical LLM rule-learning agent: learn/solve modes, LIVE Sokoban, verifier-gated rules | dormant |
| `goal-recognition` | Can a model name a game's goal from one or a few frames (50-game pool) | paused |
| `benchmark-curation` | Game selection, BFS reference solutions, vetting, benchmark positioning and tags | active |
| `codex-direct-player` | Persistent direct player: baseline and baseline+ (notes) conditions | active |
| `avo-campaigns` | AVO optimizer + player + fresh solver evaluation campaigns, Docker isolation | active |
| `workbench` | Run catalog website, launch forms, batch workers | active |
| `qwen-harness` | Main thread since Oct 2026: why Qwen 3.8-27B fails (harness, size, pretraining) | active |
| `proposal` | M.Sc research proposal (Bar-Ilan CS format, Overleaf) | active |
| `harness-revamp` | One run spec over codex, claude-code, opencode, antigravity and bare harnesses | active |
| `harness2` | Score-aware Harness² edits the direct player's OpenCode harness and re-runs the adopted harness fresh | active |
| `realtime-controllers` | Real-time direction: a slow coding agent building and repairing fast controllers and Jev-style decision calls | active |
| `meetings` | Supervisor meetings; the export starts the day after the latest such entry | active |

Status values: `active`, `paused`, `dormant`, `stable`, `closed`.

## Adding an entry at the end of a work session (for AI assistants)

1. Collect the facts of the session: `git log --since=<session start> --date=short --stat`,
   `git status`, new or edited files under `docs/`, and new run folders under
   `output/`, `avo/output/`, `studies/codex_agent/output/` (read their small
   summary files such as `result.json`, `evolution_summary.json`, `run_spec.json`).
2. If an entry for today and the same topic exists, update it; otherwise create
   `docs/diary/<today>-<slug>.md`. One entry per meaningful session or topic.
3. Fill the front matter: threads from the registry, commit SHAs, doc paths,
   and only those runs that were not started today (today's runs are linked
   automatically).
4. Write `Did / Found / Decided / Next` as short bullets. `Found` holds results
   with numbers and their source; `Decided` holds choices made and why;
   `Next` holds the concrete next steps (the export shows only the latest
   `Next` per thread).
5. Validate by saving through `PUT /api/workbench/diary/<slug>` or by checking
   that `GET /api/workbench/diary` lists the entry with no `errors`.
6. After a supervisor meeting, add an entry tagged `meetings` that records what
   was agreed. The next export then starts from the following day.

## Supervisor export

`GET /api/workbench/diary/export?from=YYYY-MM-DD&to=YYYY-MM-DD&thread=<id>&format=md|html`

Without `from`, the period starts after the latest `meetings` entry (or two
weeks before `to`). The HTML version is print-ready: open it and use
Print → Save as PDF for an A4 handout.
