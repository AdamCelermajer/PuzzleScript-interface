# Whole-run AVO loop

Operator entry point: `/runs/avo.html` in the workbench launches one or parallel
Docker campaigns. The native command below describes the controller interface;
use the Docker route on Windows. See `../../../harnesses/README.md`.

The outer loop evaluates complete player-agent packages.

```text
x_i = STRATEGY.md + inherited seed
R_i = one fresh, 500-action research run using x_i
V_i = up to two provisional fresh solver self-checks available to the inner player
S_i = solver.py alone in a second fresh environment, with its own action budget
f(x_i) = levels_completed(S_i)
```

The outer optimizer designs `x_0001` from one frozen initial observation. After each
evaluation it can page through complete research, self-check, and final-evaluation events,
including full boards and transitions. It can inspect, fork, register, and evaluate
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
  --fresh-solver-max-environment-steps 1500 `
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
│   │   └── self_check/
│   ├── solver/
│   ├── evaluation/
│   └── summary.json
└── x_0002/
```

For PuzzleScript, research progress is diagnostic only. The scalar fitness is the number of
levels completed by the fresh solver. The research evidence, transcript, final workspace,
fresh solver trace, and score are retained with each evaluation.

The research, self-check, and final fresh-solver budgets are deliberately separate.
Each inner session may run at most two self-checks; neither owns fitness. The inner receives
only each self-check's scalar fitness, while the framework retains its full trace for trusted
outer-loop inspection. Exhausting the research budget completes x_i; it does not reduce the
1,500 actions available to the autonomous held-out solver. Failed evaluations remain in
`lineage.json` and must become evidence for the outer optimizer's next candidate rather than
triggering a new top-level run directory.

Fresh play uses a framework-owned streaming loop. The evaluator sends one JSON line
containing the current `observation`; the persistent `solver.py --play` process returns one
`{"action":"ACTION_ID"}` line. The evaluator owns all real environment execution. No growing
history is resent and no per-action subprocess is started.

The outer optimizer and every inner player have independent Codex session bundles.
The held-out fresh solver is not a Codex session: its complete JSON-line interaction,
stdout, stderr, environment evidence, and score remain under `evaluation/`.
See `../LAB.md` for the session artifact contract, including the exact model
requests captured automatically for every outer and inner Codex session.
