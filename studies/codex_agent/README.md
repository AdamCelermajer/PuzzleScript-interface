# Codex SDK Agent

This experiment replaces the custom ReAct loop with one persistent Codex SDK
session.

The first turn says "solve the game" and includes the initial ARC frame. Every
later turn sends the result of the previous action plus the new frame. Codex
returns exactly one next action. There are no experiment-owned tools, notes,
probe trees, rule languages, or separate planning loop.

The model-facing prompt deliberately omits the backend game ID/title and does
not explain what the opaque `ACTION1`, `ACTION2`, etc. controls do. Their effects
must be inferred from observed transitions. The backend retains the real game ID
only for routing and artifact metadata. Codex also runs from an opaque temporary
working directory so artifact folder names cannot reveal the game identity.

The `baseline-plus` condition keeps the same persistent session, prompt, frame
feedback, and one-action output. Its only addition is a persistent note workspace
with three tools: `list_notes`, `read_note`, and `write_note`. Codex can use those
tools during a turn and then return the next game action. The condition requires
Codex to create `strategy.md` before its first action, read it on later turns, and
update it when evidence or the plan changes. Only its three audited note tools are
automatically approved. Shell and computer-use tools remain disabled. Codex may
still advertise generic internal tools; these are allowed by the user for the
September 5 Luna comparison and their use is recorded, not represented as a
strict notes-only tool inventory. Both conditions use the same internal settings.
Recent CLI versions expose the note tools through native client-side `tool_search`.
Baseline+ permits that discovery step; every returned tool is still checked against
the same allowlist. This does not enable shell execution or web search.
Every successful note write also creates an immutable numbered snapshot under
the run's `note_history/` directory. That directory is outside the model-visible
workspace, so version logging does not provide the agent with extra memory.
`note_history/note_transitions.jsonl` records the complete before/after content
and unified diff for every note write.

Every run also writes two passive audit logs. `transitions.jsonl` records the
complete before/action/after transition, including changed cells and the final
winning transition. `codex_session.jsonl` records every item returned by the
Codex SDK for each turn, including final action responses, note-tool calls,
timing, token usage, and any reasoning summary exposed by the service. It does
not contain private chain-of-thought, which is not exposed to the harness.
`isolation_manifest.json` records the model-facing isolation configuration for
contamination auditing. Frame images are copied to a generic filename inside
the opaque temporary session directory before being attached.
Outgoing requests are recorded under `model_requests/` for inspection. Recording
does not gate execution. Normal runs have no request-content or tool-inventory
guard, and do not enforce a provider response schema. The runner accepts one
action name or JSON, including prose and Markdown around JSON. An unusable reply
gets a correction turn on the same frame, counted against the decision budget
but not the game-action budget.

## Harness ladder

`--harness` changes only how the model is driven; the condition, prompt text,
reply parser, frame feedback, note workspace and audit logs stay identical.

| Harness | Transport | How tools reach the model |
|---|---|---|
| `codex` (H2, default) | Codex SDK thread | Codex MCP note tools plus Codex internals |
| `tools` (H1) | OpenRouter chat completions | `list_notes`/`read_note`/`write_note` as native function tools |
| `raw` (H0) | OpenRouter chat completions | no tool schema; `<write_note path="...">` style tags in the reply are executed |

For `baseline` (no notes) H0 and H1 are the same plain conversation. H0/H1 need an
`openrouter/vendor/model` ID, send only the newest frame image, drop the oldest
exchanges past `HARNESS_CONTEXT_CHARS` (default 240000 characters), retry transient
provider errors, and log every call to `model_session.jsonl` and `model_requests/`.
`max` effort is sent to OpenRouter as `xhigh`; `isolation_manifest.json` records both.

`--provider SLUG` pins one OpenRouter provider with fallbacks disabled, for all three
harnesses (the Codex request proxy injects the same routing field). Without it
OpenRouter routes to the cheapest endpoint, which for small open models is often an
fp4/fp8 or undisclosed quantization, and can differ between runs.

```powershell
uv run python -m studies.codex_agent.run --no-window --game-id ps_modality-v1 `
  --model openrouter/qwen/qwen3.8-27b --effort high --condition baseline-plus `
  --harness tools --provider deepinfra --max-steps 300
```

## New-session continuation

`--continue-from PARENT_RUN --max-steps 50` starts a separate continuation after
an unsolved parent exhausts its action budget or fails after recorded actions. Keep the same model, effort,
condition, and game and choose a fresh output directory. The runner replays and
verifies every prior environment transition, carries over note files and visible
action/observation history, then allows 50 additional actions. Replay actions
are recorded separately in `restoration.json`; they do not consume the new
decision budget. This is not the same persistent Codex conversation and does not
restore its private reasoning. Keep the original result and continuation result
separate when reporting the experiment.

OpenAI models reuse the Codex OAuth sign-in on this machine. Models named
`openrouter/vendor/model` use the existing `OPENROUTER_API_KEY` from `.env`
or the environment. Both routes support baseline+ notes and `--effort max`.

On Windows, the runner automatically uses the newest Codex CLI bundled with the
installed Codex desktop app so current models work with the same OAuth session.
Use `--codex-bin` only if you want to override that executable.

## Run

Start the local PuzzleScript stack:

```powershell
npm run local
```

In another terminal:

```powershell
uv run python -m studies.codex_agent.run --game-id ps_sokoban_basic-v1 --max-steps 50

# Baseline plus persistent note tools
uv run python -m studies.codex_agent.run --game-id ps_sokoban_basic-v1 --model gpt-5.5 --effort medium --max-steps 100 --condition baseline-plus
```

Run a bounded parallel matrix by repeating `--model`, `--effort`, and
`--condition`. This example launches at most three isolated runs at once and
performs three repeats at each reasoning effort:

```powershell
uv run python -m studies.codex_agent.batch `
  --game-id ps_sokoban_basic-v1 `
  --model gpt-5.5 `
  --effort minimal --effort low --effort medium `
  --condition baseline-plus `
  --repeats 3 `
  --parallel 3 `
  --max-steps 100
```

Each child run has an opaque `run-####` directory containing its normal
artifacts plus `stdout.log`, `stderr.log`, and `batch_outcome.json`. The batch
root contains `batch_config.json` and a final `summary.json`. Ctrl+C terminates
active children and prevents queued runs from starting.

The defaults are `gpt-5.6-sol` with `low` reasoning effort, which corresponds
to Sol with Light reasoning in the Codex app.

Use `--no-window` for a headless run. Outputs are written under
`studies/codex_agent/output/<run-id>/`.

The maintained browser launcher is `/runs/codex.html`. Run `npm run workbench`,
choose games, models, efforts, conditions, repeats and concurrency, then review
and launch the batch. New runs appear on `/`; results and direct-player replay
are under `/runs/results.html`. New workbench batches write to `output/workbench/`.
The CLI default output location remains unchanged. Continuation is available for
unsolved runs that exhausted their action budget and preserves the parent settings.

## Boundaries

- One Codex SDK thread is kept alive for the whole game episode.
- Each turn receives the integer grid and, when available, the rendered PNG.
- The ARC environment is the authority on whether the game is solved.
- Codex runs read-only with approvals denied. Baseline+ adds only its isolated
  note-tool server. Shell/browser integrations are disabled, but generic internal
  Codex tools may still be advertised; inspect captured requests and tool traces.

## NanoGPT provider

Set `NANOGPT_API_KEY` in the project `.env` or environment. Choose **NanoGPT** in
workbench's model picker, or pass `--model nanogpt/<model-id>` to the direct player.
For example, `--model nanogpt/deepseek/deepseek-v4.1-flash --effort high`.
Use an exact model ID from NanoGPT's catalog. The `codex`, `tools`, and `raw`
harnesses all support this provider, including baseline+ notes and continuation.
The Codex harness uses Responses; raw/tools use Chat Completions. Requests and
catalog discovery use `https://nano-gpt.com/api/v1`, matching
[NanoGPT's API setup guide](https://nano-gpt.com/api).

`--provider` pins an OpenRouter upstream and must be left empty for NanoGPT.
NanoGPT `max` reasoning effort is preserved. Provider credentials stay in the
trusted controller and are omitted from request artifacts and model shell tools.
