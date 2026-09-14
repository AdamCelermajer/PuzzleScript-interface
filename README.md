# PuzzleScript Research Workbench

A local workbench for running AVO campaigns and persistent Codex players against
PuzzleScript through an ARC-compatible interface, then inspecting their evidence.

## Start here

```powershell
npm install
uv sync
npm run workbench
```

Open [Runs](http://127.0.0.1:5173/). The launcher starts the Node runtime (3543),
ARC service (8000), Workbench API (8010), and Vite website (5173). It reuses
recognized services already on those ports; it does not stop them. Closing its
terminal stops only the processes that launcher created. Experiment workers and
Docker campaigns have their own lifetime; stop a workbench-owned batch from Runs.

The website alone (`npm run website:dev` or `scripts/start-website-monitor.ps1`)
is not the full workbench: run discovery, launch controls and the paper library
require the Workbench API too. Live AVO trace routes are provided by Vite's local
dev server; `website:build` produces the static pages, not a standalone live backend.

## Workflows

| Page | Purpose |
| --- | --- |
| Runs (`/`) | All active AVO/Codex runs, grouped by batch; process status and last evidence |
| AVO (`/runs/avo.html`) | Review and launch one or several independent Docker campaigns |
| Codex player (`/runs/codex.html`) | Baseline/baseline+, game/model/effort/repeat matrices, and new-session continuation |
| Results (`/runs/results.html`) | Compare individual outcomes and open their traces and artifacts |
| AVO console (`/experiments/avo-lab.html`) | Candidate lineage, research and fresh evaluation frames, logs, artifacts and architecture |
| Research | Papers, notes, goal recognition, optimal path and other studies |
| Historical | The old rule-learning client and its architecture |

AVO launches require the existing `avo-puzzlescript-isolated:local` Docker image
and an existing Codex OAuth login. See [Docker setup](avo/docker/README.md).
Use `http://host.docker.internal:8000` for the host ARC backend from Docker.
Parallel campaigns are independent per-game lineages; they do not share research.
Only fresh autonomous solver evaluation owns AVO fitness. Research levels are
separate diagnostic evidence.

The direct Codex player uses the existing Codex OAuth login. Baseline+ enables
its persistent note tools. Continuation creates a separate session/run, verifies
replayed transitions and retains the parent game, model, effort and condition;
the entered action budget is additional. See [player details](studies/codex_agent/README.md).

Launch forms show the run count, concurrency, time limit and exact commands before
launch. They do not start model calls during preview. Stop controls act only on
batches created by the workbench; externally owned experiments are monitor-only.

## Source ownership

- `website/`: navigation, launch forms, run/result pages and AVO trace viewer.
- `workbench/`: local API, artifact catalog and bounded experiment workers.
- `avo/`: AVO controller, isolated Codex sessions, research/evaluation and Docker launch.
- `studies/codex_agent/`: maintained direct-player runner, notes and continuation.
- `puzzlescript_interface/`: Node game engine and ARC-compatible Python service.
- `client/arc/`: shared ARC adapter/types used by AVO and the direct player.
- `client/engine/` and `client/runtime/`: historical rule-learning client; some utilities remain shared.
- `studies/`: other research studies; `avo/legacy/` and `studies/old_react/` preserve earlier approaches.
- `benchmark/`: benchmark server and scoring tools; see its [README](benchmark/README.md).

New workbench artifacts go under `output/workbench/<batch>/run-NNNN/`. Existing
artifacts stay where they are: the catalog also reads `output/`, `avo/output/`,
and `studies/codex_agent/output/`, excluding copied controller trees and workspaces.
Generated `output/` and `outputs/` are ignored by Git. Already tracked historical
artifacts remain tracked; no archive is deleted or silently migrated.

## Other entry points

```powershell
npm run local                         # Node + ARC service, no workbench
npm run benchmark:local               # benchmark stack
uv run python -m client.play_arc_client --game-id ps_sokoban_basic-v1
uv run python -m studies.codex_agent.run --game-id ps_sokoban_basic-v1 --condition baseline-plus
uv run python -m studies.codex_agent.batch --game-id ps_sokoban_basic-v1 --repeats 3 --parallel 3
```

The historical rule agent uses OpenRouter (`OPENROUTER_API_KEY`). Official ARC
runs require `ARC_API_KEY`; local games do not. Copy `.env.example` only if these
optional settings are needed. The maintained Codex workflows use OAuth.

## Checks

```powershell
uv run python -m pytest tests/workbench avo/tests/test_docker_launch.py -q
node --test tests/workbench/run-paths.test.mjs
npm run website:build
npm test
```

[Workbench architecture and status semantics](docs/architecture/workbench.md)
