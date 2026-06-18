# Client

`client/` contains the ARC-compatible command-line entry points and the shared agent runtime.

## Main Scripts

- `run_arc_agent.py` runs the unified rule-learning and solving agent against an ARC-compatible backend, including the local PuzzleScript service and the official ARC-AGI-3 endpoint.
- `screen_dashboard.py` renders the engine run in a window with the real PuzzleScript PNG and the ARC/ascii frame.
- `play_arc_client.py` lets a human play a local ARC-compatible PuzzleScript game from the terminal with keyboard controls.
- `terminal_dashboard.py` is retained only for the manual terminal play client.

## Rules Output

During runs, the agent writes two main artifacts under `client/rules/<game-id>/`:

- `timeline.jsonl` is the chronological evidence stream: states, actions, and observed transitions.
- `rules.json` is the structured rule source used for simulation.

Each accepted rule has a `ruleID`, a natural-language summary, a logical rule (`action`, `anchor`, `conditions`, `effects`), evidence statistics (`supports`, `contradictions`, `prediction_hits`, `prediction_failures`), and `revision_count`. The planner uses the logical rule directly: a rule applies when its action matches and its relative cell conditions match the current grid.

Action choice is engine-first, then LLM-guided: the planner simulates with accepted logical rules when they can reach the goal, and otherwise asks the LLM for one exploratory action. The engine records the real transition afterward. If existing rules do not explain it, the inducer asks the LLM for candidate rules using only natural-language rule summaries as prior context; the verifier tests those candidates against the timeline and only accepted candidates are stored.

For a readable debug view of rules plus timeline evidence, run:

```bash
uv run python -m client.inspect_rules --game-id ps_sokoban_basic-v1 --recent 5
```

LIVE-style experiments now live under `studies/LIVE_framework/`; goal-recognition experiments live under `studies/goal_recognition/`.
