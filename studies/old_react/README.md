# Old ReAct Agent

This folder preserves the custom ReAct experiment that preceded
`studies/codex_agent/`.

It is kept as a historical reference so the original approach remains visible:

- a Kimi-specific LLM client with thinking disabled;
- a custom JSON tool protocol;
- inspect, file, Python-helper, action-sequence, and probe-tree tools;
- per-run observations, history, tool history, and transcripts;
- custom action/tool budgets and repeated-action rejection.

This is no longer the active website agent. The current live path is
`studies/codex_agent/`, which uses one persistent OAuth-authenticated Codex SDK
session and asks for one action per frame.

The archived runner can still be invoked manually if a Kimi key is supplied:

```powershell
$env:REACT_AGENT_KIMI_API_KEY = "..."
uv run python -m studies.old_react.run --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --max-steps 50
```

Outputs are ignored under `studies/old_react/output/`.
