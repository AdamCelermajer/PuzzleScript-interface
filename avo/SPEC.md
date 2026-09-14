# AVO runtime contract

## Actors

- The player is one persistent Codex session with one isolated workspace.
- The environment gateway executes opaque actions and records real transitions.
- The fresh evaluator runs the delivered solver without Codex assistance.
- The optional outer optimizer creates and evaluates complete player runs `x_i`.

## Player run

The player receives:

- the task and environment prompt;
- its inherited workspace seed;
- observation, history, probe, reset, checkpoint, restore, status, archive, and finish
  commands;
- fixed environment-action, wall-time, and Codex-turn budgets.

The player owns all files in its workspace. There is no required internal theory,
hypothesis, branch, manifest, or candidate format.

The required deliverable for PuzzleScript is `solver.py`. In persistent `--play` mode it
reads the current observation and returns one action. It retains any necessary hidden-state
history inside the process.

Research actions do not contribute to final fitness.

## Fresh evaluation

The evaluator starts a second fresh environment and launches only one persistent `solver.py`
process. It owns real action execution and sends each resulting observation back to the
solver. Fitness is the number of levels completed in that fresh game.

The research and fresh-evaluation action budgets are independent.

## Outer evolution

Each `x_i` is one complete strategy plus inherited workspace seed. The outer optimizer:

1. designs `x_0001` from a frozen initial observation without gameplay access;
2. lets the player implement and run at most two provisional fresh self-checks;
3. evaluates `x_i` through an independent fresh solver evaluation;
4. inspects any page of its research, self-check, or final transition history;
5. forks the solver workspace into `x_(i+1)`;
6. changes the next strategy or seed;
7. continues until success or the configured outer evaluation limit.

An unsuccessful `x_i` remains part of the lineage. It does not trigger a replacement
top-level `v2` or `v3` run.

## Authority and safety

- Only the environment profile determines progress, success, and terminal state.
- Codex cannot edit trusted evidence or execute environment actions outside the gateway.
- Checkpoint identifiers are opaque and reveal no hidden state.
- The solver cannot access research checkpoints or the research environment during fresh
  evaluation.
- Registered outer candidates and evaluation records are framework-owned.
