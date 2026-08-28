# Whole-run AVO loop

The outer loop evaluates complete player-agent packages.

```text
x_i = STRATEGY.md + inherited seed
R_i = one fresh, 300-action research run using x_i
S_i = solver.py alone in a second fresh environment, with its own action budget
f(x_i) = levels_completed(S_i) * prospective_model_score(S_i)
```

The outer optimizer can inspect, fork, register, and evaluate `RunCandidate`
packages. It has no environment actions. The existing player agent retains the
environment tools, evidence, checkpoints, optional executable theory packages,
supervisor, and task evaluator.

PuzzleScript example:

```powershell
uv run python -m avo.evolve `
  --profile puzzlescript `
  --set game_id=ps_midas-v1 `
  --max-evaluations 6 `
  --player-max-environment-steps 300 `
  --fresh-solver-max-environment-steps 1500 `
  --player-max-theory-candidates 10 `
  --optimizer-max-agent-turns 30
```

Output:

```text
avo/output/evolution/<run>/
├── evolution_config.json
├── lineage.json
├── outer/
│   └── drafts/
├── x_0001/
│   ├── manifest.json
│   ├── STRATEGY.md
│   ├── seed/
│   ├── research/
│   ├── solver/
│   ├── evaluation/
│   └── summary.json
└── x_0002/
```

For PuzzleScript, research progress is diagnostic only. The scalar fitness is
the fresh solver's completed levels multiplied by its prospective transition-model
score. The model score weights exact next-state accuracy three times more than
partial observation similarity. The research evidence, transcript, final workspace,
fresh solver trace, and both scores are retained with each evaluation.

The research and fresh-solver budgets are deliberately separate. Exhausting the
research budget completes x_i; it does not reduce the number of actions available to
the autonomous held-out solver. Failed evaluations remain in `lineage.json` and must
become evidence for the outer optimizer's next candidate rather than triggering a new
top-level run directory.

Fresh play uses a framework-owned streaming loop. The evaluator sends one JSON line
containing the current `observation` and fresh-run `history`; `solver.py --play` returns
one `{"action":"ACTION_ID"}` line. The evaluator, not the solver process, owns all real
environment execution.
