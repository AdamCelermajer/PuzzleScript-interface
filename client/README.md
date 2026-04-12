# Client

`client/` contains the ARC-compatible command-line entry points and the shared agent runtime.

## Main Scripts

- `run_arc_agent.py` runs the learning or solving agent against an ARC-compatible backend, including the local PuzzleScript service and the official ARC-AGI-3 endpoint.
- `play_arc_client.py` lets a human play a local ARC-compatible PuzzleScript game from the terminal with keyboard controls.
- `terminal_dashboard.py` renders the live terminal UI used by both the automated agent runner and the manual play client.

## Rules Output

During learning runs, the agent writes inferred rule summaries to `client/rules/`, typically as `<game>_rules.txt`. These files are the saved rule artifacts reused by later solve runs and for inspection.
