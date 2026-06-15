# Client

`client/` contains the ARC-compatible command-line entry points and the shared agent runtime.

## Main Scripts

- `run_arc_agent.py` runs the unified rule-learning and solving agent against an ARC-compatible backend, including the local PuzzleScript service and the official ARC-AGI-3 endpoint.
- `screen_dashboard.py` renders the engine run in a window with the real PuzzleScript PNG and the ARC/ascii frame.
- `play_arc_client.py` lets a human play a local ARC-compatible PuzzleScript game from the terminal with keyboard controls.
- `terminal_dashboard.py` is retained only for the manual terminal play client.

## Rules Output

During runs, the agent writes readable evidence and rule artifacts under `client/rules/<game-id>/`: `transitions.jsonl`, `rules.json`, `rules.md`, and `journal.md`.

Action choice is engine-first, then LLM-guided: the planner uses verified executable rules when they can reach the goal, and otherwise asks the LLM for one exploratory action. The engine records the real transition afterward and immediately tries to induce rules for unexplained outcomes, so the LLM proposal becomes evidence instead of trusted truth.

LIVE-style experiments now live under `studies/LIVE_framework/`; goal-recognition experiments live under `studies/goal_recognition/`.
