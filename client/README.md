# Client

`client/` contains the ARC-compatible command-line entry points and the shared agent runtime.

## Main Scripts

- `run_arc_agent.py` runs the learning or solving agent against an ARC-compatible backend, including the local PuzzleScript service and the official ARC-AGI-3 endpoint.
- `play_arc_client.py` lets a human play a local ARC-compatible PuzzleScript game from the terminal with keyboard controls.
- `terminal_dashboard.py` renders the live terminal UI used by both the automated agent runner and the manual play client.

## Rules Output

During learning runs, the agent writes readable evidence and rule artifacts under `client/rules/<game-id>/`: `transitions.jsonl`, `rules.json`, `rules.md`, and `journal.md`.

Action choice is engine-first, then LLM-guided: the planner uses verified executable rules when they can reach a goal, and otherwise asks the LLM for a small subgoal and short legal action plan. The engine still records the real transition afterward, so the LLM proposal becomes evidence instead of trusted truth.

LIVE-style experiments now live under `studies/LIVE_framework/`; goal-recognition experiments live under `studies/goal_recognition/`.
