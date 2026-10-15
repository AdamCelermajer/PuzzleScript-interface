# Direct player (baseline / baseline-plus)

One persistent agent session plays one game episode. The first turn says "solve
the game" and includes the initial frame; every later turn sends the result of the
previous action plus the new frame (integer grid in text, PNG as an image). The
agent returns exactly one next action. The ARC environment decides whether the
game is solved.

The session runs over any harness from `harnesses/` (`codex`, `claude-code`,
`opencode`, `antigravity`, `bare`), always inside one Docker container per run.
Launch it with the host launcher, never directly on the host:

```powershell
uv run python -m harnesses.launch --mode baseline-plus --harness claude-code `
  --model claude-haiku-5-5 --effort low --game-id ps_modality-v1 `
  --backend-url http://host.docker.internal:8000 --max-steps 50
```

Inside the container `harnesses.entry` runs `studies.codex_agent.run` with the
run spec's arguments. See `harnesses/README.md` for harnesses, credentials and limits.

The model-facing prompt omits the game ID/title and does not explain what the
opaque `ACTION1`, `ACTION2`, ... controls do. The agent works in a temporary
directory outside the results tree.

## Conditions

- `baseline`: conversation only. The workspace holds the current `frame.png`; after
  every turn the controller deletes every other workspace file, so only the
  conversation persists. The agent still has its harness's normal tools.
- `baseline-plus`: the same, plus a `notes/` directory that is kept between turns
  and described in the system prompt (write `notes/strategy.md` before the first
  action, re-read and update it as evidence arrives). After every turn `notes/` is
  mirrored to the run's `workspace/notes/`.

## Artifacts

`run_spec.json` (launcher), `run_config.json`, `transitions.jsonl` (every
before/action/after transition), `transcript.jsonl` (prompts, parsed replies,
results), `agent_events.jsonl` (normalized harness events, schema
`agent-event-v1`), `raw/turn-<n>.jsonl` (raw CLI stdout per turn), `turns.jsonl`,
`session.json`, `system_prompt.txt`, `isolation_manifest.json`, `frames/`,
`result.json` and `world_model.json` (final report turn).

An unusable reply gets a correction turn on the same frame, counted against the
decision budget but not the action budget. `--max-wall-seconds` (0 = unlimited)
stops the run between turns.

## New-session continuation

`harnesses.launch --continue-from PARENT_RUN --max-steps 50` (baseline modes)
starts a separate continuation after an unsolved parent exhausted its action
budget or failed after recorded actions. Keep the same harness, model, effort,
condition and game, with a fresh output directory. The runner replays and verifies
every prior transition, carries over note files (into `notes/`) and the visible
action/observation history, then allows 50 additional actions. This is a new
conversation, not the original one; report the two results separately.

## Batches

`uv run python -m studies.codex_agent.batch` runs a bounded matrix, one
`harnesses.launch` container per child run (`--harness`, repeated `--model`,
`--effort`, `--condition`). The maintained browser launcher is the workbench.
