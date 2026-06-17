# Goal Recognition Evaluation Design

## Purpose

Evaluate how well LLMs infer game goals from ARC-AGI-3 observations.

The experiment is deliberately about goal recognition, not solving. The pipeline collects visual evidence from each game, asks an LLM to describe the likely goal, stores the prediction, then lets a human verify the prediction while playing the game.

The first target is the official ARC-AGI-3 backend, either all games or a limited batch of about 30 games.

## Experiment Setups

### Setup 1: One Frame

For each game:

1. Open the ARC environment.
2. Reset the game.
3. Capture the first observation frame.
4. Ask the LLM to infer the goal from that single frame.
5. Save the frame, prompt metadata, raw LLM output, and normalized prediction.

This setup measures what the model can infer from initial visual structure only.

### Setup 2: Ten Random Frames

For each game:

1. Open the ARC environment.
2. Reset the game.
3. Capture the initial frame.
4. Execute up to 10 random legal actions.
5. Capture each resulting frame and action.
6. Ask the LLM to infer the goal from the trajectory.
7. Save the trajectory, prompt metadata, raw LLM output, and normalized prediction.

Random actions are intentional for the first version. They keep this setup cheap and scalable, and they avoid mixing goal recognition with an LLM exploration policy. Later, a separate setup can let the LLM choose the 10 actions if that becomes useful.

## Directory Layout

The evaluation code lives outside `client/` so it remains a side experiment instead of becoming part of the main agent runtime.

```text
side_quests/
  one_frame_goal_recognition/
    __init__.py
    run.py
    prompt.py
    artifacts/

  ten_frame_goal_recognition/
    __init__.py
    run.py
    prompt.py
    artifacts/

  goal_recognition_review/
    __init__.py
    review.py
    report.py
```

The two setup directories are independent enough for parallel implementation. The review directory is shared and should be implemented after both runners agree on the prediction artifact format.

## Reused Repo Contracts

Use existing ARC and LLM wrappers instead of building new API clients:

- `client.arc.arcade_env.ArcadeEnv` for reset and step against local or official ARC backends.
- `client.arc.types.FrameData` as the normalized observation contract.
- `client.engine.llm_client.LlmClient` for OpenRouter JSON calls.
- `arc_agi.Arcade.get_environments()` for game discovery when running all games.
- `client.play_arc_client` control mapping and terminal play behavior as the base for manual review.

The evaluation runners may live outside `client/`, but they should import these existing contracts directly.

## CLI Shape

One-frame runner:

```bash
python -m side_quests.one_frame_goal_recognition.run ^
  --backend-url https://three.arcprize.org ^
  --games all ^
  --limit 30
```

Ten-frame runner:

```bash
python -m side_quests.ten_frame_goal_recognition.run ^
  --backend-url https://three.arcprize.org ^
  --games all ^
  --limit 30 ^
  --steps 10 ^
  --seed 1
```

Useful common options:

- `--game-id <id>` runs one game.
- `--games all` discovers games from the backend.
- `--limit N` caps the run.
- `--resume` skips games already present in the output JSONL.
- `--out <path>` overrides the artifact directory.
- `--api-key <key>` overrides `ARC_API_KEY`.

Manual review:

```bash
python -m studies.goal_recognition.review.review ^
  --predictions side_quests/one_frame_goal_recognition/artifacts/<run_id>/predictions.jsonl ^
  --backend-url https://three.arcprize.org
```

Report:

```bash
python -m studies.goal_recognition.review.report ^
  --runs side_quests/one_frame_goal_recognition/artifacts/<run_id>/predictions.jsonl ^
         side_quests/ten_frame_goal_recognition/artifacts/<run_id>/predictions.jsonl
```

## Artifact Format

Each runner writes a run directory:

```text
artifacts/
  <run_id>/
    manifest.json
    predictions.jsonl
    errors.jsonl
    frames/
      <game_id>.json
```

`manifest.json` stores run-level metadata:

```json
{
  "run_id": "2026-05-12T12-00-00-one-frame",
  "setup": "one_frame",
  "backend_url": "https://three.arcprize.org",
  "purpose": "one_frame",
  "model": "openrouter/openai/gpt-oss-120b:nitro",
  "limit": 30
}
```

`predictions.jsonl` stores one row per game:

```json
{
  "game_id": "ls20",
  "setup": "one_frame",
  "frames_seen": 1,
  "actions_taken": [],
  "available_actions": ["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
  "state": "PLAYING",
  "levels_completed": 0,
  "win_levels": 1,
  "prediction": {
    "goal_guess": "Move the player to the marked target.",
    "win_condition_guess": "The level is completed when the player/object reaches the target cell.",
    "key_objects": [
      {"value": 2, "role_guess": "player"}
    ],
    "confidence": 0.4,
    "uncertainties": ["Only one frame was observed."]
  },
  "manual_verification": null,
  "raw_response": {}
}
```

For ten-frame runs, `actions_taken` contains the random actions in order and `frames_seen` is the number of captured frames.

The separate `frames/<game_id>.json` file stores the full observed frame or trajectory. This keeps `predictions.jsonl` readable while preserving enough evidence to audit each LLM answer later.

## Prompt Contract

Both setup prompts ask for JSON only:

```json
{
  "goal_guess": "short plain-English goal",
  "win_condition_guess": "observable condition that would mean success",
  "key_objects": [
    {"value": 2, "role_guess": "player"}
  ],
  "confidence": 0.0,
  "uncertainties": ["what cannot be known from the evidence"]
}
```

The prompt should show the numeric grid values exactly as the LLM sees them. It should not include game source code, game names as semantic hints, readme files, or known solutions. The goal is visual/trajectory inference, not metadata lookup.

## Manual Verification

The review tool loads a predictions JSONL file and iterates game by game.

For each game it should:

1. Show the game id, setup, LLM goal guess, win-condition guess, confidence, and uncertainties.
2. Open the playable ARC environment.
3. Let the user play using the existing keyboard mapping.
4. Accept a verification command:
   - `c` means the inferred goal is correct.
   - `w` means the inferred goal is wrong.
   - `p` means partially correct.
   - `s` skips the game.
   - `n` adds a short note.
5. Update the prediction row or write a reviewed copy with `manual_verification`.

Manual verification is the source of truth. The pipeline does not try to auto-grade goal guesses in the first version.

## Reporting

The report script reads reviewed prediction files and creates:

- A CSV summary.
- A PNG graph comparing one-frame and ten-frame accuracy.
- Counts by verification label: correct, wrong, partial, skipped.

The basic graph should compare setups on manually verified accuracy:

```text
setup         correct   partial   wrong   skipped
one_frame     ...
ten_frame     ...
```

Partial correctness should be counted separately, not silently merged into correct.

## Error Handling

Keep failures visible and simple:

- If a game cannot open, write one `errors.jsonl` row and continue.
- If reset or stepping fails, write one error row and continue.
- If the LLM returns invalid JSON, save the raw response in `errors.jsonl`.
- `--resume` should skip completed game ids, not try to repair partially written rows.

Do not add broad recovery layers in the first version. The point is to get an auditable experiment running quickly.

## Parallel Work Split

Two workers can implement independently:

- Worker 1 owns `side_quests/one_frame_goal_recognition/`.
- Worker 2 owns `side_quests/ten_frame_goal_recognition/`.

They should not edit each other's directories. Both should follow the artifact and prompt contracts in this document.

After both runners exist, implement `side_quests/goal_recognition_review/` against the shared `predictions.jsonl` format.

## Non-Goals

- No automatic semantic grading.
- No source-code or readme inspection by the LLM.
- No changes to the main `client/` agent loop.
- No LLM-chosen exploration in the first ten-frame setup.
- No broad benchmark dashboard in the first version.
