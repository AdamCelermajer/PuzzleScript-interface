# Workbench ownership and run lifecycle

`website/` is the operator interface. FastAPI `workbench/` owns catalog discovery
and launch plans; `workbench.experiment_job` owns each launched batch as a separate
process. Its `job.json` records the configuration, children, heartbeat, statuses
and exit codes. API restarts leave those workers running. Stop requests and the
batch time limit cancel queued children and stop only owned processes/containers.

AVO children invoke `avo.docker.launch --campaign`; that launcher retains the
existing Linux isolation preflights, temporary OAuth credentials and cleanup.
Codex children invoke `studies.codex_agent.run --no-window`. Game/model/effort/
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
- `/experiments/avo-lab.html?run=...`: AVO lineage, frames, logs and artifacts.
- `/experiments/rule-agent.html`: preserved historical rule-learning workflow.

The six-game and three-game one-off monitoring pages now point to Runs. Their
original campaign artifacts and recovery scripts remain available. Explicit saved
AVO recovery/continuation remains a separate workflow; the new AVO form launches
fresh campaigns only. Imported external jobs are monitor-only, so a workbench
button cannot stop an experiment owned by another launcher.

Static build output still requires local services for live APIs. Vite serves the
AVO trace bridge; FastAPI serves run catalogs, launch controls and paper storage.
The workbench launcher reuses recognized occupied service ports and refuses an
unknown owner rather than killing it. A frontend-only server is insufficient.


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
launcher, sandbox, request guard and fresh-solver evaluator for both OpenAI and
OpenRouter models. Unprefixed model IDs use the existing Codex OAuth login;
`openrouter/vendor/model` uses the project OpenRouter API key. Player and optimizer
can select providers independently. See [AVO Docker setup](../../avo/docker/README.md).

The OpenCode POC launcher, Zen catalog and separate replica are retired. New
requests reject that backend, and saved jobs cannot restart it. Existing experiment
results retain their recorded identities. A small reader in
`website/history/opencode-events.js` displays their archived conversation logs.

## Campaign builder and matched comparisons

The builder groups game selection, models, condition and budgets into separate
sections. Codex is used throughout; the model picker offers OpenAI via Codex login
and OpenRouter for AVO. Baseline+ retains its existing OpenAI path. Search,
free-only filtering, context limits and prices apply to the OpenRouter catalog;
a manual model ID remains available. Tool support alone does not establish full
Codex compatibility. DeepSeek V4.1 Flash was live-tested on September 14.

`GET /api/workbench/model-catalog?provider=openrouter` fetches the public catalog
without credentials. Responses are cached for ten minutes; failed refreshes retain
the previous list with a stale notice. No model calls happen during catalog
browsing or launch preview. The historical rule-agent model endpoint is unchanged.

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
