# PuzzleScript Learning Benchmark

This benchmark measures two things:

1. **Rule learning** — can the agent predict `f2` from a saved
   `<f1, action, f2>` transition?
2. **Closeness** — how close is the last unfinished level to a verified
   solution?

Goal recognition and the previous solving score are not part of v0.4.

## Folder structure

Every game owns its reusable evaluator artifacts:

```text
benchmark/
  games/
    index.json
    ps_sokoban_basic-v1/
      game.json
      levels/
        level-000/
          solution.json
          rule-probes.json
          closeness.json
```

- `solution.json` contains the replay-verified action sequence.
- `rule-probes.json` contains unique hidden transitions from the verified
  solution trace plus bounded nearby exploration. Selection covers distinct
  fired rule families first, then prefers actual solution transitions.
- `closeness.json` contains the frames on the verified solution trace, their
  remaining action distance, and normalized closeness.

The current artifact set contains 21 games and one verified selected level per
game for closeness. All 21 games provide 10 unique rule probes. When the
verified level is too short, the rule probe generator samples additional
transitions from other levels in the same game instead of duplicating probes.

## Webpage

Start the local stack and open `http://127.0.0.1:9000`:

```powershell
npm run benchmark:local
```

The webpage is the evaluator console. It shows:

- artifact coverage for every game;
- live rule-learning and closeness scores;
- each game's current board, budget, and level closeness;
- pending and submitted rule challenges;
- the rule-learning curve across checkpoints;
- the full evaluator event stream and result JSON.

No benchmark score depends on terminal output.

The **Watch random agent** and **Watch partial agent** buttons launch background
runs. The page refreshes twice per second while each agent waits 0.5 seconds
between actions.

## Reference agents

Reference agents live under `benchmark/agents/`:

```text
agents/
  random/
    agent.py
  simulated_partial/
    agent.py
    scenario.json
```

The random agent is a genuine action-only baseline. The partial fixture is
different: it deliberately uses evaluator artifacts to manufacture a stable
dashboard example. Its result is clearly marked as a fixture and must not be
reported as a real benchmark submission.

## Rule-learning protocol

A rule challenge can be attached to:

- level start;
- every 10 environment actions;
- level completion;
- budget exhaustion.

The agent receives only the probe ID, `before_frame`, and action:

```json
{
  "benchmark_challenge": {
    "challenge_id": "challenge-000001",
    "checkpoint": "level_start",
    "probes": [
      {
        "probe_id": "challenge-000001:level-0-step-3",
        "before_frame": [[0, 2, 1]],
        "action": "ACTION4"
      }
    ]
  }
}
```

It submits the hidden `f2` predictions separately:

```http
POST /api/benchmark/runs/{run_id}/rule-challenges/{challenge_id}
X-API-Key: {run_token}
Content-Type: application/json

{
  "predictions": [
    {
      "probe_id": "challenge-000001:level-0-step-3",
      "predicted_frame": [[0, 1, 2]]
    }
  ]
}
```

The primary score is the latest macro exact-frame accuracy across tested
games. Cell accuracy, changed-cell F1, exact transition-edit F1, answer
coverage, and the full learning curve are also retained.

## Closeness protocol

For a level with a verified solution of length `D`, a saved trace state at
solution step `s` has:

```text
closeness = s / D
remaining_actions = D - s
```

A completed level is always 100%.

The current exact artifacts cover only frames on the saved verified solution
trace. If an agent reaches a frame outside that trace, closeness is reported as
`unavailable` and excluded from the mean. It is never treated as zero.

Later, a full reverse-distance graph can replace this trace lookup without
changing the public score shape.

## Artifact generation

The checked-in artifacts are reusable; normal benchmark runs do not regenerate
them. To rebuild the current set from the existing verified references:

```powershell
npm run benchmark:artifacts
```

The general “add a new game, solve all levels, and generate every artifact”
pipeline is intentionally left for a later version.
