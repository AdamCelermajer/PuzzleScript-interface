# Frameworks

A **framework** is one agent method; a **harness** (`harnesses/`) is the coding CLI its
agents run on. Every run is one framework × one harness × one model, launched as one
Docker container by `python -m harnesses.launch`.

| id | folder | what it is | options | restart |
|---|---|---|---|---|
| `baseline` | `baseline/` | the coding agent plays directly, one action per turn | `max_steps`, `notes` (on = "Baseline+") | `--continue-from PARENT` into a new directory |
| `avo` | `avo/` | an optimizer agent evolves a player's strategy; each candidate's `solver.py` is scored by a fresh run | `max_evaluations`, `research_moves`, `solver_moves`, `world_model_mode`; plus `--optimizer-model/--optimizer-effort` | `--resume` in the same directory |

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

## Outputs

New CLI runs default to `output/<framework>/<run>`; workbench launches use
`output/workbench/<job>/run-NNNN`. Runs from before this layout stay where they were
recorded (`avo/output/`, `studies/codex_agent/output/`); the catalog still reads them, and
`run_spec.json` files with the older `run-spec-v1` schema (`mode`: baseline, baseline-plus,
campaign) map to `baseline` (notes off/on) and `avo`.
