# ReAct Agent Experiment

This folder contains a contained experimental agent that observes the same
ARC-compatible PuzzleScript frames as the main client, but can create its own
notes, helper scripts, and private rule language inside a per-run workspace.

## Command

Set a ReAct-specific Kimi key before running. The experiment intentionally
does not read the main engine's `OPENROUTER_API_KEY`.

```powershell
$env:REACT_AGENT_KIMI_API_KEY = "..."
```

By default the experiment calls `https://api.kimi.com/coding/v1`. Override with
`REACT_AGENT_KIMI_BASE_URL` if you have a Moonshot platform key for a different
Kimi-compatible endpoint.

```powershell
uv run python -m studies.react_agent.run --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --max-steps 50
```

The default command opens the same `tkinter` screen dashboard used by the main
engine runner. Use `--no-window` for a headless console run.
The default model is `kimi-k2.6`; override it with `--model`.
Thinking is disabled by default for the ReAct-local Kimi client.
Use `--max-non-action-tools 1` or `2` to control how much thinking/tool use the
agent may do before it must try a movement action.
The agent may use `take_action_sequence` for multi-step plans; every action in
the sequence still counts against `--max-steps`.

Outputs are written under `studies/react_agent/output/<run-id>/` by default.

## Boundaries

- The prompt includes current frames, recent action/history, and workspace file names.
- It does not include PuzzleScript source, solution files, or existing `client/rules` artifacts.
- File tools are contained to the run workspace.
- Python helper execution runs from the workspace with a short timeout.
