# Direct player (framework `baseline`: Baseline / Baseline+)

One persistent agent session plays one game episode. The first turn says "solve
the game" and includes the initial frame; every later turn sends the result of the
previous action plus the new frame (integer grid in text, PNG as an image). The
agent returns exactly one next action. The ARC environment decides whether the
game is solved.

The session runs over any harness from `harnesses/` (`codex`, `claude-code`,
`opencode`, `antigravity`, `bare`), always inside one Docker container per run.
Launch it with the host launcher, never directly on the host:

```powershell
uv run python -m harnesses.launch --framework baseline --notes --harness claude-code `
  --model claude-haiku-5-5 --effort low --game-id ps_modality-v1 `
  --backend-url http://host.docker.internal:8000 --max-steps 50
```

Inside the container `harnesses.entry` runs `frameworks.baseline.run` with the
arguments `framework.py` builds from the run spec. Without `--output-dir` the run
goes to `output/baseline/<run>`. See `harnesses/README.md` for harnesses,
credentials and limits.

The model-facing prompt omits the game ID/title and does not explain what the
opaque `ACTION1`, `ACTION2`, ... controls do. The agent works in a temporary
directory outside the results tree.

## Options

`--max-steps` (default 200) and `--stop-after-levels` (default 0, play on).

- Both drivers get the same prompt, word for word (`prompt.py`, since 2 Nov 2026): the same system
  prompt, the same observation text (status, available actions with `RESET` among them, grid), the
  same first message and the same final world-model report. Only one line differs: how a move is
  sent, `act` once per turn for the controller, `look` and `do` for the agent. OpenCode gets these
  as real tools (custom tools in its private config) that run the same scripts (`act.py`,
  `game.py`); the other harnesses run the scripts through their shell. Before 2 Nov the two
  prompts differed (reset, image path, notes, scripts, world model, solver).
- The controller keeps one conversation per game and deletes nothing between turns; after every
  turn `notes/` is mirrored to the run's `workspace/notes/`.
- `world_model.md`, when the agent writes one, is copied to `world_model_snapshots/` every 100
  game actions, after each completed level (`a0100.md`, …, `level-<k>-a<NNNN>.md`) and at the end
  (`final.md`). Nobody asks for it during play; at the end the agent writes it as a report, also
  saved as the run's `world_model.md`.

With `--driver agent` (`agentic.py`) two more options apply:

- `--start FOLDER`: a repository folder (e.g. `studies/thursday/start/rules`) copied into the
  run as `start/` before the container starts; the agent's folder begins with exactly those
  files (an `AGENTS.md` there reaches OpenCode as instructions).
- `--stop-after-levels N`: the game ends once N levels are completed. The move that completes
  level N prints only `LEVEL COMPLETED (N/M). Level target reached; the game is over.`; the next
  level is never printed or saved to `frame.png`, and that move's record (whose after-frame is
  the next level) is written only after the session. Then the usual world-model and solver turns run.

A provider failure of a turn is followed by another turn ("The last reply failed; continue …");
an error that ends the conversation itself (NanoGPT's "Invalid request parameters" for a full
context) continues in a fresh session in the same folder. Three failed turns in a row end the
run with an error; `result.json` lists them under `failed_turns`.

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

`harnesses.launch --framework baseline --continue-from PARENT_RUN --max-steps 50`
starts a separate continuation after an unsolved parent exhausted its action
budget or failed after recorded actions. Keep the same harness, model, effort,
notes setting and game, with a fresh output directory. The runner replays and verifies
every prior transition, carries over note files (into `notes/`) and the visible
action/observation history, then allows 50 additional actions. This is a new
conversation, not the original one; report the two results separately.

## Batches

`uv run python -m frameworks.baseline.batch` runs a bounded matrix, one
`harnesses.launch` container per child run (`--harness`, repeated `--model`,
`--effort`, `--notes off|on`). The maintained browser launcher is the workbench.
