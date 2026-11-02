# Workbench revamp contract (2026-10-15)

Shared interfaces for the parallel revamp. Every part of the revamp builds against
this file; change it only together with every consumer.

## 1. Harnesses

| harness id    | CLI / loop                 | providers            | model strings                                   | credentials in container |
|---------------|----------------------------|----------------------|-------------------------------------------------|--------------------------|
| `codex`       | `codex exec --json`        | openai               | bare OpenAI ids, e.g. `gpt-5.6-sol`             | `~/.codex/auth.json` copied into `$CODEX_HOME` |
| `claude-code` | `claude -p --output-format stream-json --verbose` | anthropic | `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1` | env `CLAUDE_CODE_OAUTH_TOKEN` (from `.env`) |
| `opencode`    | `opencode run --format json` | openrouter, nanogpt | `openrouter/<vendor>/<model>`, `nanogpt/<model>` | env `OPENROUTER_API_KEY` / `NANOGPT_API_KEY` (from `.env`) |
| `antigravity` | `agy -p --output-format stream-json` | google      | ids from `agy models`, e.g. `gemini-3.8-flash-high` | docker volume `puzzlescript-agy-home` mounted at the agent's `~/.gemini`, filled once by `python -m harnesses.launch login antigravity` |
| `bare`        | in-process tool-calling chat loop (former H1) | openrouter, nanogpt | same as opencode | env API key, kept in the controller process |

Every harness:
- is resumable: first turn creates a session; later turns resume it by id
  (codex `exec resume <thread_id>`, claude `--session-id`/`--resume`, opencode `--session`, agy `--conversation`);
- runs with permission prompts disabled (Docker is the sandbox): codex
  `--dangerously-bypass-approvals-and-sandbox`, claude `--dangerously-skip-permissions`,
  opencode `--dangerously-skip-permissions` + `opencode.json` `permission`, agy `--dangerously-skip-permissions`;
- has web search / web fetch / browser tools disabled (the games are public; looking
  them up invalidates the run);
- receives the same system prompt text (appended/first-turn as the CLI allows);
- maps one effort value `low|medium|high|xhigh|max` to its own flag
  (codex `-c model_reasoning_effort=`, claude `--effort`, opencode `--variant`, agy `--effort`);
- writes, per run, the raw CLI stdout under `<analysis>/raw/turn-<n>.jsonl` and the
  normalized event log below.

Verified 2026-10-15 on Windows: all four CLIs ran headless, made a shell tool call and
returned session ids. OpenCode needs the requested model declared in `opencode.json`
(`provider.<p>.models.<id> = {}`) when models.dev does not know it (e.g. `qwen/qwen3.8-27b`).
**Never touch the host OpenCode install** (`~/.local/share/opencode`, `~/.config/opencode`,
the global npm `opencode`): T3 Code depends on it. Runs use the OpenCode inside the Docker
image; any host-side test sets throwaway `XDG_DATA_HOME`/`XDG_CONFIG_HOME`/`XDG_STATE_HOME`/
`XDG_CACHE_HOME` and never installs, upgrades or configures the global `opencode`.
`agy` prints harmless `http: TLS handshake error from 127.0.0.1` lines on stderr.

### Normalized agent event log — `agent_events.jsonl`

One JSON object per line, same schema for every harness:

```json
{"schema": "agent-event-v1", "t": "2026-10-15T09:00:00Z", "session": "<harness session id>",
 "role": "player|optimizer", "turn": 3,
 "type": "message|reasoning|command|file_change|tool|image|usage|error|turn_end",
 "text": "human readable text or command", "output": "command/tool output (truncated 16k)",
 "exit_code": 0, "tool": "name for type=tool", "usage": {"input": 0, "output": 0, "reasoning": 0, "cached": 0},
 "harness": "claude-code", "model": "claude-sonnet-5-5"}
```

Only `schema`, `t`, `role`, `turn`, `type`, `harness` are required.

## 2. Frameworks and the run spec

Frameworks (`frameworks/registry.py`; interface `Framework`/`Option` in `frameworks/base.py`):
`baseline` (direct play; option `notes` adds a `notes/` directory in the workspace, shown as
"Baseline+") and `avo` (AVO optimizer + player + solver evaluation). The former modes map as
`baseline` → `baseline`, `baseline-plus` → `baseline` with `notes: true`, `campaign` → `avo`.

Baseline workspace: one conversation per game, and nothing is deleted between turns; the CLI keeps
its own tools. `notes` adds a `notes/` directory and asks the agent to keep its working memory
there (21 Oct 2026; before that, every file except the frame and `notes/` was deleted after each turn).

Every run output directory gets `run_spec.json`:

```json
{"schema": "run-spec-v2", "framework": "avo",
 "options": {"max_evaluations": 8, "research_moves": 400, "solver_moves": 400,
             "world_model_mode": "final-only"},
 "harness": "opencode", "model": "openrouter/qwen/qwen3.8-27b", "effort": "high",
 "optimizer_model": "openrouter/qwen/qwen3.8-27b", "optimizer_effort": "high",
 "game_id": "ps_modality-v1", "backend_url": "http://host.docker.internal:8000",
 "provider": "", "max_wall_seconds": 0, "continued_from": null,
 "created_at": "2026-10-15T09:00:00Z"}
```

`max_wall_seconds: 0` means unlimited. `options` holds every option of the framework with
defaults filled in; `optimizer_model`/`optimizer_effort` are `null` for frameworks without an
optimizer. The older `run-spec-v1` (`mode` + `budget` + `world_model_mode`) is still read for
old runs. The container entry (`harnesses/entry.py`) calls
`framework.entry(spec, resume, /results, /parent)`.
Existing per-mode files (`run_config.json`, `evolution_config.json`, ...) stay; `run_spec.json`
is added next to them and is what the workbench reads first.

## 3. Launch command (host side)

```
uv run python -m harnesses.launch
  --framework {baseline,avo} --harness {codex,claude-code,opencode,antigravity,bare}
  --model M --effort E [--optimizer-model M] [--optimizer-effort E]   # optimizer: avo only
  --game-id G --backend-url URL [--output-dir DIR]   # default output/<framework>/<run>
  [--max-wall-seconds S]                      # 0 = unlimited, default 0
  [--max-steps N] [--notes]                   # baseline options
  [--max-evaluations N --research-moves N --solver-moves N --world-model-mode final-only|between-hypotheses]  # avo options
  [--provider SLUG]                           # OpenRouter upstream pin (opencode/bare only)
  [--resume]                                  # avo (restart="resume"): continue the campaign saved in DIR
  [--continue-from PARENT_DIR]                # baseline (restart="continue"): replay parent, new DIR
uv run python -m harnesses.launch login antigravity   # interactive one-time login into the volume
uv run python -m harnesses.launch check [--harness H] # credential + image readiness, JSON on stdout
```

`harnesses.launch` builds and runs exactly one Docker container (image
`puzzlescript-agents:local`, all four CLIs + Python controller deps, non-root user `agent`).
Container: controller code read-only at `/controller` (no games, no `.env`), results bind at
`/results`, `--cap-drop ALL`, `no-new-privileges`, memory/cpu/pids limits, normal network.
No Codex sandbox, no request proxy, no ACL tricks. Controller code staged: `client`,
`frameworks`, `harnesses`. New CLI runs default to `output/<framework>/<run>`; older runs stay
under `avo/output/...` and `studies/codex_agent/output/...`, which the run catalog still reads.

## 4. Workbench HTTP API (FastAPI, prefix `/api/workbench`)

The SPA talks only to FastAPI (Vite only proxies). Former Vite dev-only routes
(`/__avo/*`, `/__games/*`, `/__notes/save`, `/__pseudocode/save`) move into FastAPI.

- `GET  /harnesses` → `[{id, label, providers, models:[{id,label}], efforts, ready, missing}]`
- `GET  /frameworks` → `{frameworks:[{id, label, description, options:[{name, flag, kind, default,
  help, choices, minimum, maximum}], optimizer, artifact, restart}]}`
- `POST /runs/preview` body RunRequest → `{runs:[{framework,options,variant,harness,model,game_id,command,...}], warnings}`
- `POST /runs` body RunRequest → `{job_id}`; RunRequest =
  `{frameworks:[{id, options}], harnesses[], models[], optimizer_model?, optimizer_effort?, efforts[],
    games[], repeats, parallel, max_wall_seconds, provider?, label?}` (matrix over list fields; the
  same framework may appear twice with different options, e.g. notes off and on)
- `POST /runs/resume` `{run_id}` → avo `--resume` or baseline `--continue-from`
- existing `/catalog`, `/record`, `/record/timeline`, `/record/file`, `/submission*`,
  `/experiments/{stop,pause,dismiss,log}` stay; `/record` exposes `agent_events` when present
- `GET /benchmarks`, `GET /benchmarks/{game_id}`, `PATCH /benchmarks/{game_id}`,
  `POST /benchmarks/{game_id}/play` + `POST /benchmarks/play/{session}/{action}`
- `GET /diary?thread=&from=&to=`, `GET /diary/{slug}`, `PUT /diary/{slug}`,
  `GET /diary/export?from=&to=&thread=&format=md|html`

## 5. Game metadata — `benchmark/games.json`

```json
{"schema": "games-v1",
 "tag_vocabulary": {"mechanics": ["push", "..."], "properties": ["hidden-state", "..."]},
 "games": {"ps_modality-v1": {
   "title": "Modality", "author": "", "homepage": "",
   "status": "playable|excluded", "exclusion_reasons": [],
   "collections": ["selection-20", "selection-v0", "reference"],
   "tier": "easy|medium|hard|null", "tier_source": "selection-20|selection-v0|manual|null",
   "levels": 4, "structure": {"objects": 0, "rule_groups": 0, "max_area": 0},
   "bfs": {"solved": true, "depth": 12} ,
   "tags": {"mechanics": [], "properties": []}, "tags_status": "draft|reviewed|none",
   "summary": "one-line mechanic summary", "notes": ""}}}
```

Agent solve rates are computed live by the API from the run catalog, never stored here.

## 6. Diary — `docs/diary/`

One markdown file per entry, `YYYY-MM-DD-<slug>.md`, front matter:

```yaml
---
date: 2026-10-15
title: Workbench and harness revamp
threads: [harness-revamp]
runs: []          # run ids / output paths, optional; API also links runs started that day
commits: []       # short SHAs
docs: []          # repo-relative paths
reconstructed: false
---
## Did
## Found
## Decided
## Next
```
