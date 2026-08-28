# Whole-run AVO loop

The outer loop evaluates complete player-agent packages.

```text
x_i = STRATEGY.md + seed workspace
R_i = one fresh research run using x_i
S_i = solver.py alone in a second fresh environment
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
  --max-evaluations 5 `
  --player-max-environment-steps 1000
```

Output:

```text
avo/output/evolution/<run>/
├── evolution_config.json
├── population.json
├── candidates/x_0001/
├── evaluations/x_0001/run_001/
└── optimizer_workspace/
```

For PuzzleScript, research progress is diagnostic only. The scalar fitness is
the fresh solver's completed levels multiplied by its prospective transition-model
score. The model score weights exact next-state accuracy three times more than
partial observation similarity. The research evidence, transcript, final workspace,
fresh solver trace, and both scores are retained with each evaluation.
