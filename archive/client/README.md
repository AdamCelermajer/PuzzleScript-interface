# Shared ARC client and historical rule agent

`client/` contains the ARC-compatible command-line entry points and the shared agent runtime.

## Main Scripts

- `run_arc_agent.py` runs the unified rule-learning and solving agent against an ARC-compatible backend, including the local PuzzleScript service and the official ARC-AGI-3 endpoint.
- `run_arc_agent.py` runs headlessly and prints progress logs; the historical browser interface is `/experiments/rule-agent.html`.
- `screen_dashboard.py` provides the optional desktop display used by the direct Codex CLI and older runners.
- `play_arc_client.py` lets a human play a local ARC-compatible PuzzleScript game from the terminal with keyboard controls.
- `terminal_dashboard.py` is retained only for the manual terminal play client.

## Rules Output

During runs, the agent writes four main artifacts under `client/rules/<game-id>/`:

- `timeline.jsonl` is the chronological evidence stream: states, actions, and observed transitions.
- `rules.json` is the structured rule source used for simulation.
- `natural_rules.json` stores natural-language hypotheses independently of executable rules.
- `rule_failures.jsonl` records each compact compile/verification failure and process stop.

Each accepted rule has a `ruleID`, a natural-language summary, a logical rule (`action`, `anchor`, `conditions`, `effects`), evidence statistics (`supports`, `contradictions`, `prediction_hits`, `prediction_failures`), and `revision_count`. The planner uses the logical rule directly: a rule applies when its action matches and its relative cell conditions match the current grid.

Action choice is engine-first, then LLM-guided: the planner simulates with accepted logical rules when they can reach the goal. If no rule plan exists, it asks the LLM for a subgoal first, then makes a separate LLM call for the next action plan. The engine records the real transition afterward.

Rule learning is also split into two LLM steps. First, the inducer asks for natural-language rule hypotheses using only previous natural-language rule summaries as prior context; that prompt does not include the executable rule schema. Second, supported hypotheses are compiled into executable rule candidates. The verifier tests those candidates against the timeline and only accepted candidates are stored.

For a readable debug view of rules plus timeline evidence, run:

```bash
uv run python -m client.inspect_rules --game-id ps_sokoban_basic-v1 --recent 5
```

LIVE-style experiments live under `studies/LIVE_framework/`; goal-recognition
experiments live under `studies/goal_recognition/`; the persistent direct-play
agent (framework `baseline`) lives under `frameworks/baseline/`; the previous custom ReAct
implementation is archived under `studies/old_react/`.

## Maintained AVO Framework

The maintained AVO implementation lives under `frameworks/avo/` (framework `avo`),
including its client, generic kernel, profiles, prompts and tests. Older run
artifacts remain in `avo/output/`.

Launch AVO campaigns and direct-play runs with `python -m harnesses.launch` (one Docker container per run); see `harnesses/README.md`.
