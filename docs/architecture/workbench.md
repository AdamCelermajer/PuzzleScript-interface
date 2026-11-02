# Workbench ownership and run lifecycle

`website/` is the operator interface. FastAPI `workbench/` owns catalog discovery
and launch plans; `workbench.experiment_job` owns each launched batch as a separate
process. Its `job.json` records the configuration, children, heartbeat, statuses
and exit codes. API restarts leave those workers running. Stop requests and the
batch time limit cancel queued children and stop only owned processes/containers.
Setting `max_hours` to zero disables the scheduled batch cutoff. For AVO this
passes zero wall limits to the campaign and research player as well; action,
candidate, and solver self-check budgets still apply. Manual stops remain active.

New batches (`POST /api/workbench/runs`, below) invoke `uv run python -m harnesses.launch`
and have no batch cutoff: each run owns `max_wall_seconds` (0 = unlimited), and the
worker only backstops a child that outlives its wall by the 600 s report grace. Legacy
`/experiments` batches keep `max_hours`, as described above.

Legacy AVO children invoke `avo.docker.launch --campaign`; that launcher retains the
the existing Linux sandbox, temporary OAuth credentials and cleanup. Isolation probes are explicit diagnostics.
Legacy Codex children invoke `frameworks.baseline.run --no-window`. Game/model/effort/
condition/repeat combinations are separate child runs, with configurable bounded
concurrency. The workbench does not introduce shared model memory or change fitness.

The registry reads known artifact roots without relocating data and prunes copied
controllers, agent workspaces, candidates and traces during discovery. Docker is
queried for currently running AVO containers and their results mounts. A recent
workbench worker heartbeat confirms the status it reports. Old session files
saying `running` do not prove current liveness; such archives are `unconfirmed`.
A final artifact confirms a recorded result, independently of process status.
AVO fitness comes from lineage evaluations, never research progress or game names.

The original AVO console uses this catalog and accepts a run ID identifying the
actual campaign directory. Old single-folder links remain valid. Path resolution
rejects traversal and linked directories. Fresh evaluation, research and their
frames/logs remain distinct. The direct-player detail page supports recorded
action-by-action grid replay and artifact downloads, with polling of the latest
transition when following a live run.

Current routes:
- `/`: active and queued runs by default, with all/history filters.
- `/runs/avo.html`: supported Docker AVO campaign launcher.
- `/runs/codex.html`: direct-player matrix and continuation launcher.
- `/runs/results.html`, `/runs/detail.html`: outcomes and direct-player evidence.
- `/games/`: benchmark library with manual play, per-game experiments, reviewed rules,
  agent world models, level annotations and goal-recognition answers.
- `/experiments/avo-lab.html?run=...`: AVO lineage, frames, logs and artifacts.
- `/experiments/rule-agent.html`: preserved historical rule-learning workflow.

The six-game and three-game one-off monitoring pages now point to Runs. Their
original campaign artifacts and recovery scripts remain available. Explicit saved
AVO recovery/continuation remains a separate workflow; the new AVO form launches
fresh campaigns only. Imported external jobs are monitor-only, so a workbench
button cannot stop an experiment owned by another launcher.

Static build output still requires local services for live APIs. FastAPI serves run
catalogs, launch controls, the AVO trace bridge (`/api/workbench/avo/*`), notebook saves
and paper storage; Vite only proxies (the old `/__avo/*`, `/__notes/save` and
`/__pseudocode/save` paths are proxy rewrites until the UI calls the new paths).
The workbench launcher starts/reuses the [Docker backend](docker-backend.md).
Local workbench/frontend services reuse recognized occupied ports and refuse an
unknown owner rather than killing it. A frontend-only server is insufficient.

Run `npm run workbench` in one persistent terminal, or use the existing
`PuzzleScript Website` shortcut. The launcher checks the PuzzleScript runtime
(3543), ARC service (8000), Workbench API (8010), Vite website (5173), the
frontend API proxy, and the configured Tailscale URL. The website is a production
build served by `vite preview` and rebuilt by `vite build --watch` on every source
change (reload the page to pick it up); `WORKBENCH_WEB_DEV=1` serves the Vite dev
server with hot reload instead, which is much slower on a laptop. It starts only missing
local services and rechecks them every five seconds. Backend containers are started
once at launch; an explicit Docker stop is respected until the user starts them again.
Existing healthy local processes are
reused, including an API whose command line Windows does not expose when its
health response identifies it. A failed check is printed in the terminal and
retried without stopping the other services; closing the terminal stops only
local processes that launcher started. The shared backend has its own explicit stop.
Use `scripts/start-workbench.ps1 -LocalBackend` for the original host backend when
debugging (stop Docker's backend first).

The benchmark library joins the current 20-game selection, the earlier 30-game
curation and the 21-game reference catalog by exact game ID. It retains their
collection memberships and keeps reviewed mechanic notes separate from agent
inferences. Agent experiments use the shared run catalog and browser visibility
preferences. Goal studies, historical rule archives and saved BFS results are read
from their existing locations. Missing records remain explicit.

`website/game-library-server.mjs` supplies `/__games/catalog`, `/__games/detail`
and `/__games/play` through Vite. Manual play uses the existing engine in a
dedicated worker per session, with a 15-second response timeout, 30-minute idle
expiry and explicit close. It never uses campaign sessions, writes research logs,
or restarts shared game services. Playable level numbers exclude message screens.

Play is always expanded. Reviewed rules and source-derived level notes support
double-click editing, Save (Ctrl/Cmd+Enter) and Cancel (Escape). `POST /__games/notes`
updates `output/game-selection-20/selection.json` for reviewed rules, or the
original `level-annotations.mjs` for mechanics and Midas level-focus notes. Mechanic
edits regenerate `level-annotation-detail.json` and apply across the listed levels.
Writes are serialized, check the original value for conflicts and replace files
atomically. Agent-produced experiment reports remain read-only.


## Harness run API (revamp contract §4)

All routes are under `/api/workbench`; the contract is `docs/architecture/revamp-contract.md`.

- `GET /harnesses[?catalogs=false]` → `[{id, label, providers, models:[{id,label,...}], efforts,
  ready, missing, ...}]` for `codex`, `claude-code`, `opencode`, `antigravity`, `bare`
  (`workbench/harness_catalog.py`). Codex/Claude/Antigravity model lists are static; opencode
  and bare list the public OpenRouter/NanoGPT catalogs (`catalogs=false` skips that fetch).
  `harnesses.registry` is imported lazily and may override labels/models; when it cannot be
  imported every entry reports `missing: ["harnesses package", ...]`. Readiness checks only that
  credentials exist (`.env`/environment key names, `~/.codex/auth.json`), the Docker image
  `puzzlescript-agents:local` and the volume `puzzlescript-agy-home`. Values are never returned.
- `GET /frameworks` → `{frameworks:[{id, label, description, options:[{name, flag, kind, default,
  help, choices, minimum, maximum}], optimizer, artifact, restart}]}` from `frameworks/registry.py`.
  The Launch page builds its framework cards and option editors from it; picking several values of
  a choice/bool option launches one matched run per value.
- `POST /runs/preview` and `POST /runs` take a RunRequest: `{frameworks:[{id, options}], harnesses[],
  models[], optimizer_model?, optimizer_effort?, efforts[], games[], repeats, parallel,
  max_wall_seconds, provider?, label?, backend_url?}`. The same framework may appear twice with
  different options (e.g. baseline with notes off and on). The matrix is games × frameworks ×
  (harness, model) × efforts × repeats (at most 120 runs). (harness, model) pairs whose provider does
  not match are skipped with a warning; a model no selected harness runs is an error. Options are
  checked against the framework's `Option` list; `optimizer_model`/`optimizer_effort` are rejected
  when explicitly set without a framework that has an optimizer (avo), and omitted from commands of
  frameworks without one. `provider` (OpenRouter upstream pin) is accepted only when every harness
  is opencode or bare, and only with OpenRouter models. Preview returns `{runs:[{framework, options,
  variant, harness, model, game_id, command, ...}], warnings, count, parallel}` and starts nothing;
  launch returns `{job_id, count, warnings}` and detaches one `workbench.experiment_job` worker.
  Rows sharing game/harness/model/effort/repeat share a `match_id`, so Baseline, Baseline+ and AVO
  compare within one launch. `POST /runs` without `frameworks` is still the historical rule-agent start.
- Backend URL: one setting, `backend_url` or `WORKBENCH_BACKEND_URL`, default
  `http://host.docker.internal:8000` (every harness runs in Docker). `ps_enqueue-v1` is routed to
  port 8001 on a local host because only the dedicated runtime runs `PUZZLESCRIPT_METHOD=ondemand`.
- `POST /runs/resume {run_id}` → `{job_id, run_id, ...}`. Follows the framework's `restart`: an avo
  campaign is copied (as recovery always did) into a new batch and continued with `--resume`; a
  baseline run gets a new directory with `--continue-from <parent>`. Settings come from `run_spec.json`, else the legacy config.
  Active, already-resumed, solved/finalized, needs-assistance, legacy-Enqueue and `bare-raw`/
  `opencode (legacy)` runs are refused (409/400). `/experiments/resume?job=` and
  `/experiments/resume-run?run=` remain as aliases of this path (service tiers are ignored).
- Catalog rows read `run_spec.json` first (`run-spec-v2`, or v1 `mode` + `budget` for old runs;
  also from a campaign's parent run directory) and add `framework`, `variant` (Baseline|Baseline+|
  AVO), `options`, `max_wall_seconds`, `harness` (legacy `tools`→`bare`, `raw`→`bare-raw
  (legacy)`, `opencode`→`opencode (legacy)`), `effort`, `optimizer_effort`, `provider`,
  `spec_source`, `continued_from`, `resumable`. Old v1 modes and legacy conditions map to
  `baseline` (notes off/on) and `avo`. The results matrix filters by `variant`. Runs are read from
  `output/` (new CLI runs under `output/<framework>/`, workbench runs under `output/workbench/`)
  and the archives `avo/output/` and `studies/codex_agent/output/`. A run directory with only a baseline
  `run_spec.json` is discovered too. `/record` adds `run_spec`, `normalized` and `agent_events`
  (`{total, invalid_lines, truncated, events}`, tail of `agent_events.jsonl`, `events_limit`
  default 500) when present; otherwise `agent_events` is null and legacy files are listed.
- `/avo/{runs,run,frame,logs,artifacts,artifact}`, `POST /notes`, `POST /pseudocode`
  (`workbench/avo_console.py`) are ports of the former Vite middleware with the same shapes and
  `{error}` bodies. Live (latest) frames without a stored PNG are replayed by one persistent
  Node worker (`workbench/avo_replay_worker.cjs`) from saved evidence only. AVO logs fall back
  to `agent_events.jsonl` when an analysis directory has no `conversation.jsonl`.

## Campaigns and final submissions

Use `/runs/new.html` for both approaches. Baseline+ is direct play with persistent notes;
baseline without notes remains an explicit comparison condition. Neither requires a generated
solver. AVO evolves a solver through a sequential candidate lineage.

The launch matrix is games × player models × efforts × conditions × independent attempts.
Each row is a fresh campaign. “Campaigns running at once” schedules these independent rows;
it never evaluates sibling hypotheses concurrently inside one lineage. Review shows every row.

`/runs/submission.html?run=...` reads the best completed AVO evaluation. Selection matches
EvolutionStore: maximum fresh fitness, first evaluation on ties. It never substitutes the newest
draft or research progress for that solver. The two primary outputs are:

- `solver.py`: the executable entry point from the scored, archived solver directory. Its helper
  files remain part of the executable submission when used; the ZIP preserves the directory
  as `solver/` rather than pretending one Python file is always self-contained.
- `world_model.md`: the final outer optimizer report, separate from the evaluated directory.
  It describes the outer session's understanding of the game rules. It does not contribute to fitness.

New AVO campaigns support `final-only` (default) and `between-hypotheses`. Selecting both
creates separate campaigns with matched game/model/action/evaluation budgets. In the latter,
the outer is asked to update `drafts/x_i/seed/world_model.md` between hypotheses for the next
inner session. In final-only mode, no world-model instructions are added during search.
Neither mode blocks registration based on model-file presence or removes inherited notes.
In both modes, one extra call in the same outer thread requests the final report after search
closes; this call is not announced in the search prompt. Evaluation and mutation tools are closed;
population and evidence inspection remain available. The reporting call uses at most 180
seconds within the remaining wall budget. A time limit or infrastructure failure can leave
it missing; the UI reports absence instead of inventing a document.

Evaluation records include `score.search_session_elapsed_seconds` for new search sessions,
measured before final reporting. Results expose first-success evaluation count and search
seconds when available. Intermediate modeling consumes search time. Compare fresh campaigns
with repeated attempts; old/resumed campaigns are not a matched timing comparison.

Existing saved artifacts are not rewritten. Explicit campaign recovery inherits its saved
world-model condition and rejects switching conditions mid-campaign. Older campaigns retain
`off` behavior unless started anew. No experiments or paid model calls are started by previews.

The explicitly requested six-game report backfill uses `avo/report_saved_world_model.py`.
It reconstructs an expired outer session from its saved completed messages/tool outputs and
observation images, with the original base instructions, model and effort. The final request is
`Write world_model.md in your current workspace describing your understanding of the game's rules.`
The source campaign is mounted read-only and evaluation is closed. The generated report is
attached with `world_model.json` provenance; the result page and artifact viewer label it as
reconstructed from saved outer history. This does not change the campaign's original condition,
solver, scores or search timing, and is not a measurement of the original session's final beliefs.


## Run inspection and replay

Run links open the AVO run console for both active and finished campaigns. Selecting a
hypothesis opens its saved fresh-evaluation replay when available, with research selectable
separately. Playback supports initial state, previous/next action, play/pause, timeline
scrubbing, and return to the latest frame. Historical positions remain pinned during
catalog refresh. Explicit historical replay reads stored observations and PNGs (or the
recorded grid when no PNG exists), without executing game actions or invoking models.

The selected hypothesis has direct strategy, solver, and log inspection controls. Finished
campaigns also expose a final-result link. The result page opens solver source automatically;
downloads are secondary controls in a collapsed section.

## Codex and model providers

Codex is the sole maintained coding-agent runtime. AVO uses the existing Docker
launcher, sandbox, request capture and fresh-solver evaluator for OpenAI, OpenRouter, and
NanoGPT models. Unprefixed model IDs use the existing Codex OAuth login;
`openrouter/vendor/model` uses `OPENROUTER_API_KEY`; `nanogpt/model` uses
`NANOGPT_API_KEY`. Keys are read from the project `.env` or environment. Player and optimizer
can select providers independently. See [AVO Docker setup](../../avo/docker/README.md).

The OpenCode POC launcher, Zen catalog and separate replica are retired. New
requests reject that backend, and saved jobs cannot restart it. Existing experiment
results retain their recorded identities. A small reader in
`website/history/opencode-events.js` displays their archived conversation logs.

## Campaign builder and matched comparisons

The builder groups game selection, models, condition and budgets into separate
sections. Codex is used throughout; the model picker offers OpenAI via Codex login
and OpenRouter / NanoGPT for both AVO and the direct player, including baseline+. Search,
free-only filtering, context limits and prices apply to both public catalogs;
a manual model ID remains available. Tool support alone does not establish full
Codex compatibility. DeepSeek V4.1 Flash was live-tested on September 14.

`GET /api/workbench/model-catalog?provider=openrouter` (or `provider=nanogpt`) fetches the public catalog
without credentials. Responses are cached for ten minutes; failed refreshes retain
the previous list with a stale notice. No model calls happen during catalog
browsing or launch preview. NanoGPT uses the same API host for catalog discovery and inference (`https://nano-gpt.com`),
and detailed catalog prices are already USD per million tokens. OpenRouter provider
pinning is rejected for NanoGPT; leave that field empty. All three harnesses
(`codex`, `tools`, `raw`) support NanoGPT. The historical rule-agent model endpoint is unchanged.

Selecting **Compare conditions** sends `comparison: true`, fixes the conditions
to `final-only` and `between-hypotheses`, and defaults to two parallel slots.
The API accepts only 2/4/6 slots for comparisons. Each game/model/effort/attempt
combination gets an explicit `pair_id` and two independent campaign directories
in the same durable job. The worker starts a pair only when two slots are free.
Attempts are paired before scheduling the next condition; the same outer model,
inner model, efforts, world-model-independent settings and budgets apply to both.
The total launch time limit includes queued pairs, as before.

After launching, the browser opens `/runs/compare.html?job=...`. Results also links
to saved comparisons and each paired batch. `GET /api/workbench/comparison?job=...`
returns those explicit pairs, fresh solver fitness, success, first-success timing,
action use, and fitness histories. Missing values remain null; ongoing and
incomplete pairs are provisional. Curves show best fresh fitness against completed
evaluation count. Timing/action totals include completed candidate evaluations
only. Links open each run's replay and evaluated solver/report. These are descriptive
comparisons, not claims of statistical significance. Historical unpaired runs are
not silently matched or rewritten.

The Runs homepage is a live activity monitor. It reads worker status from the
catalog immediately, groups active launches newest first, and keeps parallel
conditions together in a compact list. Only current launch details are enriched through
the existing AVO snapshot/settings endpoints. Finished or failed partners remain
visible while their launch is active. Stale workers get an attention state;
unconfirmed historical archives do not count as running. Historical visibility
preferences never hide live activity. Polling does not restart any services.
Inactive resumable batches can be removed from Runs after confirmation. This records
display metadata in `job.json`; it does not delete artifacts or remove Results entries.

Results defaults to finished runs and retains optional all/active filters and
the historical comparison tools. Both pages order dated launches newest first,
independently of game name, runner or process status. Results uses compact rows
grouped by launch, keeping parallel pairs contiguous. Launch timestamps own the
order; archives without launch/start times use their labeled last activity date.

Runs and Results show fresh fitness as completed levels / total levels, with a
separate recorded solved outcome and process status. Missing evaluations remain
blank rather than zero. `website/src/run-results.mjs` joins the catalog with the
existing settings/artifact and submission APIs, preferring each fresh evaluation's
recorded level count. A current-library fallback is explicitly labeled. Archive
requests are bounded and cached by run modification time; this requires no new
service or game-engine restart.

Results offers game/outcome filters, run checkboxes, a persistent selection bar,
and one-click **Compare pair** links. Pairs retain both launch and pair identity,
including original and recovery attempts. `/runs/compare.html?view=detail&run=...&run=...`
opens a focused comparison with score cards, a fitness curve with full-level
targets, and collapsible settings/timing/evidence. **Edit selection** returns to
the selector with those run IDs. The selector defaults to parallel comparisons;
**All AVO runs** also permits explicit comparisons across models and launches.
Explicit detail URLs continue showing their selected runs if a run later fails.
Game links open `/games/?game=...` throughout these result surfaces.

## Enqueue engine backend and campaign failures

`scripts/start-enqueue-backend.ps1` owns a separate Node PuzzleScript runtime on
port 3544 with `PUZZLESCRIPT_METHOD=ondemand` and a separate ARC service on 8001.
That ARC catalog exposes only `ps_enqueue-v1`; the usual 3543/8000 services are
left alone. Launch Enqueue by itself with backend URL
`http://host.docker.internal:8001` for Docker AVO (or
`http://localhost:8001` for a local direct player). Keep the launcher running
while the campaign runs. Existing campaign artifacts keep their original engine
behavior; start a new campaign rather than mixing engine modes in one lineage.

AVO treats PuzzleScript HTTP 5xx, connection failures, and timeouts as
infrastructure failures. The active Codex turn is interrupted, the campaign
stops with `error.json` status `needs_assistance`, and the run appears in the
saved Runs list with its reason. Such a run cannot be resumed into the same
lineage; repair the backend and launch a fresh campaign. A solver that simply
does not solve the game remains an ordinary evaluated candidate.
