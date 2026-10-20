# Frameworks

A **framework** is one agent method; a **harness** (`harnesses/`) is the coding CLI its
agents run on. Every run is one framework × one harness × one model, launched as one
Docker container by `python -m harnesses.launch`.

| id | folder | what it is | options | restart |
|---|---|---|---|---|
| `baseline` | `baseline/` | the coding agent plays the game itself, no outer method; `driver` sets who drives it: `controller` (`run.py`, we send one frame per call and get one action) or `agent` (`agent.py`, the agent plays through `python game.py` in a folder that persists) | `max_steps`, `notes` (on = "Baseline+"), `driver` | `--continue-from PARENT` into a new directory (controller only) |
| `avo` | `avo/` | an optimizer agent evolves a player's strategy; each candidate's `solver.py` is scored by a fresh run | `max_evaluations`, `research_moves`, `solver_moves`, `world_model_mode`; plus `--optimizer-model/--optimizer-effort` | `--resume` in the same directory |
| `harness2` | `harness2/` | Harness²: a coach edits the harness files (AGENTS.md, skills, scripts) of an agent that plays through `game.py` in its own folder, from run outcomes; the kept harness is re-run fresh | `k`, `recursion`, `max_steps`; plus `--optimizer-model/--optimizer-effort` | `--resume` in the same directory |

The launcher, the container entry (`harnesses/entry.py`) and the workbench read only the
interface in `base.py`, through `registry.py`:

- `Option(name, kind, default, ...)`: becomes the CLI flag `--name-with-dashes`, the key in
  `run_spec.json` `options`, and an editor on the workbench Launch page. A choice or bool
  option with several selected values launches one matched run per value.
- `Framework.entry(spec, resume, results, parent)`: the module and arguments run inside the
  container.
- `optimizer`, `artifact` (subfolder the framework writes its records to, e.g. AVO's
  `campaign/`), `restart` and `check_restart`, and `variant` (display name for a set of
  options).

## Adding a framework

1. Create `frameworks/<id>/` with the code and a `framework.py` that defines one `Framework`.
2. Add it to `FRAMEWORKS` in `registry.py`.

The CLI flags, `run_spec.json`, the workbench API (`GET /api/workbench/frameworks`) and the
Launch form follow from the declaration. A framework without an `artifact` folder should
write `result.json` in the baseline shape (`status`, `solved`, `levels_completed`,
`action_count`) so the run catalog can show its outcome.

## Harness²

Uses Google Research's [Harness²](https://github.com/google-research/harness2), pinned to
`1cfe254e8d25b15f37048c3730134686abe60335`. One task is one PuzzleScript game.

The player is Baseline with `driver=agent` (`baseline/agent.py`, notes off), set up as in the paper: one OpenCode session with one task and
one working folder that persists for the whole rollout. It plays only through
`python game.py look | do ACTION | reset` in that folder; a small server in the player
process owns the game session and the action budget and records every move in the
baseline shape (`transitions.jsonl`, `frames/`, `result.json`), so the run page replays
each rollout. When the agent ends a turn with actions left it is told to continue in the
same session (two turns without an action end the rollout). At the end, with the game
closed, it writes `world_model.md` and then `solver.py` (`next_action(grid, levels_completed)`,
saved for reading, never run); both go to the coach, and its folder is kept under `workspace/`. The starting harness is
empty (stock OpenCode); candidates add `AGENTS.md`, `.opencode/` skills, agents and
plugins, and `scripts/` to the folder before the session starts.

The improver uses our installed OpenCode binary, `--optimizer-model` and
`--optimizer-effort`, capped at 120 steps per session. Parallel and sequential recursion
both expose levels completed and actions used in every trajectory. Adoption considers
all base, INV, DOM and composition rollouts: most levels, then fewer actions, then base
on an exact tie. There is no blind selector or cross-game library.

At `k=1`, each game uses **4 player runs + 1 fresh final run, 3 improver sessions**
(invalid proposals or transport failures can add improver attempts). The fresh final run
supplies the root `result.json`; `adoption.json` records base levels, best-of-pool levels,
the adopted label and every selection rollout. `recursion.json` and `improver/` retain
stage decisions and session logs. Resume reuses completed players and cached proposals;
an interrupted player restarts only its own rollout. `--max-wall-seconds` applies per
player and per improver session (0 leaves players unlimited; improvers default to 3600s).

```powershell
uv run python -m harnesses.launch --framework harness2 --harness opencode --model openrouter/qwen/qwen3.8-27b --effort low --optimizer-model openrouter/anthropic/claude-opus-4.8 --optimizer-effort high --game-id ps_modality-v1 --backend-url http://host.docker.internal:8000 --k 1 --recursion parallel --max-steps 200
```

Local tests need Python 3.12 or 3.13 and `uv sync --extra dev`; the Docker image uses 3.12.

## Outputs

New CLI runs default to `output/<framework>/<run>`; workbench launches use
`output/workbench/<job>/run-NNNN`. Runs from before this layout stay where they were
recorded (`avo/output/`, `studies/codex_agent/output/`); the catalog still reads them, and
`run_spec.json` files with the older `run-spec-v1` schema (`mode`: baseline, baseline-plus,
campaign) map to `baseline` (notes off/on) and `avo`.
