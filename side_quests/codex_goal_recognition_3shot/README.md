# OpenRouter Goal Recognition Matrix

Contained experiment for the curated 50-game local PuzzleScript goal-recognition pool.

The Python collector talks to the local ARC-compatible PuzzleScript service and saves two evidence modes for each game:

- `one_frame` - reset once and save the first observation.
- `three_random_actions` - reset once, take 3 seeded random legal actions, and save the 4-observation trajectory.

Each evidence mode gets two input modes:

- `text_only`
- `text_plus_first_image`

The Node runner sends saved prompt payloads through `llm_call(prompt)` and defaults to the OpenRouter model matrix for this experiment.

## Setup

Start the local PuzzleScript stack from the repo root:

```bash
npm run local
```

Install the local Node dependency for the Codex SDK runner:

```bash
cd side_quests/codex_goal_recognition_3shot
npm install
```

## Stage 1: Arrange Artifacts

From the repo root:

```bash
python -m side_quests.codex_goal_recognition_3shot.prepare_artifacts
```

Useful options:

- `--game-id ps_sokoban_basic-v1` arranges one game.
- `--limit 3` arranges the first 3 curated games.
- `--seed 1` controls deterministic random actions.
- `--backend-url http://localhost:8000` points at the local ARC service.
- `--no-arc` prepares static dataset artifacts and marks 3-action evidence unavailable.

Outputs are written to:

```text
side_quests/codex_goal_recognition_3shot/artifacts/<run_id>/
```

## Stage 2: Build Prompts

From the repo root:

```bash
python -m side_quests.codex_goal_recognition_3shot.build_prompts --run-dir side_quests/codex_goal_recognition_3shot/artifacts/<run_id>
```

Prompt payloads are organized for prefix caching:

- `prompt_prefix` contains the shared instructions and evidence history.
- `prompt_suffix` contains the input-mode note and fixed question.
- OpenRouter calls use a stable `session_id` per `(model, game_id, evidence_mode)`.
- Anthropic rows keep a `cache_control` breakpoint on the prefix; other models rely on automatic provider caching.

## Run OpenRouter Matrix

From this folder:

```bash
$env:OPENROUTER_API_KEY = "..."
npm run run-codex -- --run-dir artifacts/<run_id>
```

Estimate first without calls:

```bash
npm run run-codex -- --run-dir artifacts/<run_id> --estimate-only
```

Actual calls require only:

```powershell
$env:OPENROUTER_API_KEY = "..."
```

Then run:

```bash
npm run run-codex -- --run-dir artifacts/<run_id> --resume
```

The default OpenRouter matrix is:

```text
deepseek/deepseek-v4-pro        text-only rows only
moonshotai/kimi-k2.6            text and image rows
anthropic/claude-opus-4.8       text and image rows
openai/gpt-5.5                  text and image rows, reasoning effort low, max_tokens 2500
```

The runner shows a per-model rough cost estimate before calls, writes the cache-ordered execution plan to `batches/llm_plan.jsonl`, then runs without a request timeout. It can keep up to 10 LLM calls in flight, starting another call every 30 seconds while the pool is not full. It sends `max_tokens=1200` by default so providers do not reserve huge output budgets. Kimi overrides to `reasoning.effort=none`, `reasoning.exclude=true`, `include_reasoning=false`, and `max_tokens=1600` because the Kimi provider can otherwise spend the whole response on reasoning with `content:null`. GPT-5.5 overrides to `reasoning.effort=low`, `reasoning.exclude=true`, `include_reasoning=false`, and `max_tokens=2500`. Use `--resume` to skip completed `(game_id, evidence_mode, input_mode, prompt_id, model)` rows in `predictions.jsonl` and `skips.jsonl`.

Useful stage-3 options:

- `--estimate-only` prints the cost plan and makes no LLM calls.
- `--limit N` runs or estimates only the first `N` planned rows.
- `--resume` skips existing prediction and skip rows.
- `--completion-tokens-estimate 300` adjusts cost estimation.
- `--image-tokens-estimate 1000` adjusts image cost estimation.
- `--max-tokens 1200` caps model output tokens per request.
- `--concurrency 10` caps simultaneous LLM calls.
- `--launch-interval-seconds 30` controls how quickly the async pool fills.
- `--no-plan` avoids rewriting `batches/llm_plan.jsonl`.

To run a single model instead:

```bash
npm run run-codex -- --run-dir artifacts/<run_id> --client openrouter --model moonshotai/kimi-k2.6
```

## Run Codex SDK

```bash
npm run run-codex -- --run-dir artifacts/<run_id> --client codex_sdk --model gpt-5.3-codex-spark
```

## Artifact Shape

Each run contains:

```text
manifest.json
sources/<game_id>/ascii.txt
sources/<game_id>/screenshot.png
evidence/<game_id>/<evidence_mode>.json
trajectories/<game_id>/<evidence_mode>/<game_id>.json
prompts/<game_id>/<evidence_mode>/<input_mode>/goal_recognition_v1.json
batches/
predictions.jsonl
errors.jsonl
skips.jsonl
```

Each prompt payload stores:

```text
system
prompt_prefix
prompt_suffix
prompt
image_paths
```

`prompt` is exactly `prompt_prefix + prompt_suffix`. The prefix contains the shared instructions and trajectory. The suffix contains only the small input-mode note plus the fixed question, so OpenRouter/provider prefix caching can reuse the shared text across repeated model calls.

OpenRouter does not expose a native batch endpoint in the same way OpenAI does. The local separation is intentional: stages 1 and 2 produce provider-neutral artifacts, while the LLM stage can later add direct OpenAI/Anthropic batch submission without changing artifact or prompt generation.

Random movement never selects `RESET` or `ACTION7` undo. If a game exposes only those actions, collection stops after the frames gathered so far.
