# AVO

Operator entry point: start `npm run workbench` and open `/runs/avo.html` for
one or parallel Docker campaigns. Native Windows isolation currently fails
closed; the native commands below describe the controller interface, not the
supported Windows launch path. See `harnesses/README.md`.

AVO gives a persistent Codex session an isolated workspace and a small interface to an
unknown environment. Codex advances through the game as far as it can, keeping
`world_model.md`; a candidate scores the levels its research session completes (fewer
actions break ties). There is no solver: solver-scored AVO was archived on 2 Nov 2026
(`archive/avo-solver/`).

The agent decides how to use its workspace. It may create notes, scripts, simulations,
tests, intermediate representations, or temporary hardcoded transitions. The framework
does not impose an internal hypothesis format or candidate-publication workflow.

The framework owns observations, environment execution, checkpoints, budgets, terminal
detection, artifact archival, and scoring. Action IDs remain opaque.

## Layout

```text
frameworks/avo/
  framework.py                Framework declaration (options, container entry, resume)
  core/                       environment execution and evidence
  client/                     persistent Codex client
  environments/puzzlescript/ PuzzleScript adapter, prompt, and fitness
  evolution/                  outer x_i optimizer and candidate evaluation
  prompts/                    player and outer instructions
  tests/                      maintained tests
  research_score.py           a session's best level and the tie-break
  run.py                      one research run
  evolve.py                   outer sequence of research runs
```

## Run PuzzleScript

Start the local stack:

```powershell
npm run local
```

Then run one player or the outer optimizer:

```powershell
uv run python -m frameworks.avo.run --profile puzzlescript --set game_id=ps_sokoban_basic-v1
uv run python -m frameworks.avo.evolve --profile puzzlescript --set game_id=ps_midas-v1
```

Run artifacts default to `output/avo/runs/` and `output/avo/evolution/`; older runs stay
in `avo/output/`.

See `SPEC.md` for the runtime contract and `evolution/README.md` for the x_i layout.

## Session logs

Every Codex-backed run writes a session bundle outside the agent workspace. A
single run uses `<output>/analysis/`; evolution uses
`<output>/optimizer_analysis/` for the outer optimizer and
`<output>/x_NNNN/research/analysis/` for each inner player.

The bundle contains `session.json`, `prompt.json`, exact client turn inputs in
`turn_inputs.jsonl`, the unfiltered Codex notification stream in
`app_server_events.jsonl`, a role-aware `conversation.jsonl`, workspace snapshots,
and the existing compact reasoning-redacted `agent_events.jsonl`.

Exact request bodies sent from Codex to the model are captured automatically in
`analysis/model_requests/`. AVO starts a loopback capture proxy inside the AVO
process, points the ordinary Codex OAuth session through it, and stops it with
the session. Authentication headers are forwarded in memory but are never
written to the logs. There is no API key, logging flag, separate launcher, or
custom Codex binary to manage.

Session logs may contain full prompts, reasoning emitted by the server, command
output, tool results, and workspace contents. Treat the output directory as
private data.
