# AVO Docker / Linux isolation

This is the supported alternative to the failing native Windows preflight.
The Windows personal Codex config and Windows sandbox setup are never changed.

The trusted AVO controller and Codex app-server run in a clean Linux image.
Controller code is staged read-only without game sources, histories or `.env`.
The controller can contact the ARC backend and model service. Model commands and
fresh solvers run inside Codex's Linux Bubblewrap/seccomp sandbox: only their
anonymous workspace and required runtime files are readable. Results, controller
source and private credentials are excluded. The model gets structured object
grids and PNGs, not game names or object-name legends.

The Docker controller requires SYS_ADMIN, SETUID, SETGID and SETFCAP plus an
unconfined *outer* seccomp profile to create nested namespaces on this host.
This is not `--privileged`: no host devices, Docker socket or personal home are
mounted. Agent commands have zero effective capabilities, and their inner
seccomp/network and filesystem restrictions are checked through both the CLI
and app-server command paths. Do not run model commands directly in the outer
controller. A failed preflight stops execution; there is no weaker fallback.

## Build and verify (no model calls)

```powershell
docker build -t avo-puzzlescript-isolated:local avo/docker
.venv\Scripts\python.exe -m avo.docker.launch --output-dir output/avo-docker-preflight
.venv\Scripts\python.exe -m avo.docker.smoke_host
```

The image uses Python 3.12 and the locally installed `avo-jericho:local` image
only as a dependency/binary source; `/app` and `/games` are not copied into the
new image. The six-way smoke test owns a temporary Node/FastAPI stack and stops
it afterward. It exercises real ARC resets/actions and the fresh-solver stdin/
stdout protocol using two fixed test actions per game, without any LLM.

## Launch a full campaign

The browser entry point is `/runs/avo.html` after `npm run workbench`. Choose
games, player models, efforts, repeats and concurrency. Preview lists every child
campaign before launch. New batches are stored under `output/workbench/`.
The original `batch.py` and `repairs.py` remain experiment-specific recovery tools;
their one-off monitors now point to the unified Runs page.

The launcher accepts separate `--optimizer-effort` and `--player-effort`,
`--player-service-tier`, and `--max-wall-seconds`. The original `--effort` remains
a fallback. Campaign output directories must be fresh. Saved AVO recovery remains
an explicit separate workflow; the browser form launches fresh campaigns.

Use `python -m avo.docker.launch --campaign --help` for options. A campaign
requires explicit `--game-id`, `--backend-url`, `--optimizer-model`,
`--player-model`, `--max-evaluations`, `--research-moves`, `--solver-moves`, and
a fresh `--output-dir`. The backend URL must be reachable from Docker, usually
`http://host.docker.internal:PORT` for the host ARC service.

The launcher stages only a temporary copy of the existing ChatGPT OAuth login
for the trusted controller. It never mounts or edits personal Codex config.
Credentials are removed when the launcher exits; do not retain that temporary
directory. Each campaign gets its own container, private runtime and outputs.

### OpenRouter through Codex

Select the Codex harness and choose OpenRouter in either model picker, or pass
`--optimizer-model openrouter/deepseek/deepseek-v4.1-flash` and/or
`--player-model openrouter/deepseek/deepseek-v4.1-flash` to the launcher. The two
roles may use different providers. Unprefixed models retain ChatGPT OAuth.
The prefix is removed only when sending the model ID to Codex/OpenRouter.

The launcher uses `OPENROUTER_API_KEY` from the project `.env`, falling back to
the environment. `AVO_OPENROUTER_KEY_FILE` explicitly selects a credential file.
Only required credentials are staged; an all-OpenRouter campaign needs no OAuth
login. The API key reaches the trusted Codex process after the shell environment
allowlist is fixed. It is never written to Codex config or model request captures.
The existing Docker, root-deny permissions, network denial, preflights, request
guards and fresh-solver evaluation remain in use. No personal config is changed.

DeepSeek V4.1 Flash passed the September 14 side test with persistent turns,
command execution, denied private reads/network, hidden API key, and validated
request capture. A one-candidate real PuzzleScript campaign also exercised both
model roles, image inspection, two solver self-checks and a fresh solver evaluation
(two actions, exit code zero). Its tiny budget scored zero levels; the wall limit
left no time for the optional final world-model call. Evidence is under
`output/codex-openrouter-side-test-20260914/`.
Compatibility is model-specific; a tool-capable catalog entry
alone does not prove Responses, image, or long-session compatibility. OpenRouter
players cannot use the Codex `priority` service tier.

The per-run preflight executes before the outer optimizer, and the existing
per-player/per-solver preflights remain enabled. Request capture and context
guards remain unchanged.

Verified: original isolation probe, app-server command isolation, six simultaneous
real-game solver smoke tests, and authenticated outer/inner model turns for all
six games. The September 8 batch is in `output/avo-six-live-20260908-r7`;
`batch.json` contains its monitor URL and owned container names. Outer requests
use Astra low; inner requests use Luna high with priority service. Each campaign
allows 20 candidates, 300 research moves each, and 1,500 fresh solver moves.
The independent watchdog stops only these containers at 03:50 Israel time.

Private configuration disables bundled skills and optional tools. A private
model catalog retains model identities and reasoning settings while disabling
the model-metadata tool bundle override. The request guard still checks every
request. The native executable-only sandbox helper directory is an allowed
path reference; its private parent and credentials remain denied.
