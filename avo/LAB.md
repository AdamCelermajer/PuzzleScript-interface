# AVO v0.4

This is the executable kernel of the general-purpose AVO design. The complete
contract and current implementation status are defined in `SPEC.md`.

## Authority boundary

- The autonomous agent owns candidate creation, representation, parent lineage,
  tool use, experiment selection, and stop timing.
- Candidate theories are filesystem Theory Packages invoked through a JSON
  subprocess protocol.
- `AvoLaboratory` owns the immutable evidence sequence, freezes predictions
  before execution, performs the environment step, and records evaluations.
- An environment adapter owns observation comparison. The first adapter maps
  the existing ARC-compatible PuzzleScript client without exposing its legend
  or game identity.
- `DeterministicSupervisor` watches only process signals such as repeated
  no-change actions, repeated probes, and collective prospective failure.

The generic runner uses the existing Codex OAuth session. The agent gets only
the prompt, its isolated workspace, and the generic AVO tool interface.

## Layout

```text
avo/
  core/                       generic kernel, evaluator, gateway, history
  client/                     persistent Codex OAuth client
  environments/puzzlescript/ PuzzleScript adapter, prompt, and fitness
  prompts/                    environment-neutral base instructions
  tests/                      active framework tests
  legacy/                     superseded AVO experiments
  output/                     run artifacts
  run.py                      generic profile runner
```

## Run PuzzleScript

Start the local stack:

```powershell
npm run local
```

Then, in another terminal:

```powershell
uv run python -m avo.run `
  --profile puzzlescript `
  --set backend_url=http://127.0.0.1:8000 `
  --set game_id=ps_sokoban_basic-v1
```

To add a domain, create one folder under `avo/environments/` containing
`profile.toml`, `profile.py`, `adapter.py`, and `prompt.md`. The profile owns
input/output translation, the objective, task fitness, and terminal detection.
The kernel, gateway, history, supervisor, and Codex client remain unchanged.

Candidate code remains untrusted. It can predict and propose experiments, but
it does not receive write access to framework evidence. A stronger OS process
sandbox is still required before running hostile packages.

## Verified full run

`avo/output/sokoban-basic-full-v04-20260824/final_summary.json` records a complete
two-level Sokoban Basic run. The PuzzleScript profile returned `WIN` after 84
opaque environment actions in one persistent Codex turn. The agent created and
archived its own BFS solver, plan executor, compact probe utility, and notes; no
action meanings, legend, source, win condition, or solution were exposed.
