# Whole-run AVO loop

Operator entry point: `/runs/avo.html` in the workbench launches one or parallel
Docker campaigns. The native command below describes the controller interface;
use the Docker route on Windows. See `../../../harnesses/README.md`.

The outer loop evaluates complete player-agent packages.

```text
x_i = STRATEGY.md + inherited seed
R_i = one fresh, 500-action research run using x_i
f(x_i) = most levels completed during R_i (fewer actions to reach them break ties)
```

The outer optimizer designs `x_0001` from one frozen initial observation. After each
evaluation it can page through the complete research events, including full boards and
transitions. It can inspect, fork, register, and evaluate
`RunCandidate` packages but has no environment actions. The existing player agent retains the
environment tools, evidence, checkpoints, free-form workspace, supervisor, and task
evaluator.

PuzzleScript example:

```powershell
uv run python -m frameworks.avo.evolve `
  --profile puzzlescript `
  --set game_id=ps_midas-v1 `
  --max-evaluations 10 `
  --player-model gpt-5.3-codex-spark `
  --player-effort high `
  --player-service-tier priority `
  --player-max-environment-steps 500 `
  --optimizer-model gpt-5.6-sol `
  --optimizer-effort high `
  --optimizer-service-tier priority `
  --optimizer-max-agent-turns 30
```

These are the defaults: the outer `gpt-5.6-sol` session may evaluate up to ten
complete hypotheses (`x_0001` through `x_0010`). Each hypothesis gets one isolated
`gpt-5.3-codex-spark` high-effort research session with at most 500 environment
actions.

Output:

```text
output/avo/evolution/<run>/
├── evolution_config.json
├── lineage.json
├── optimizer_analysis/
│   ├── session.json
│   ├── conversation.jsonl
│   ├── app_server_events.jsonl
│   └── model_requests/
├── outer/
│   └── drafts/
├── x_0001/
│   ├── manifest.json
│   ├── STRATEGY.md
│   ├── seed/
│   ├── research/
│   │   ├── analysis/
│   │   │   ├── session.json
│   │   │   ├── conversation.jsonl
│   │   │   ├── app_server_events.jsonl
│   │   │   └── model_requests/
│   ├── solver/          final workspace (historical name), inherited by children
│   └── summary.json
└── x_0002/
```

There is no solver: the research session is the scored run (`../research_score.py`).
Solver-scored AVO, with its fresh `solver.py` evaluation and self-checks, was archived on
2 Nov 2026 (`archive/avo-solver/`). Failed evaluations remain in `lineage.json` and must
become evidence for the outer optimizer's next candidate rather than triggering a new
top-level run directory.

The outer optimizer and every inner player have independent Codex session bundles.
See `../LAB.md` for the session artifact contract, including the exact model
requests captured automatically for every outer and inner Codex session.
