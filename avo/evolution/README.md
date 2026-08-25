# Whole-run AVO loop

The outer loop evaluates complete player-agent packages.

```text
x_i = STRATEGY.md + seed workspace
R_i = one fresh player run using x_i
f(x_i) = EnvironmentProfile.evaluate(R_i).fitness
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

For PuzzleScript, scalar fitness is `levels_completed`. The full diagnostic
score, evidence, transcript, final workspace, and terminal result are retained
with each evaluation.
