# AVO runtime contract

## Actors

- The player is one persistent Codex session with one isolated workspace.
- The environment gateway executes opaque actions and records real transitions.
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

The player keeps `world_model.md` in its workspace. There is no solver.

## Score

Fitness is the most levels completed at any point of the research session; fewer actions
to reach them break ties (`research_score.py`). Solver-scored AVO (a fresh run of the
player's `solver.py`) was archived on 2 Nov 2026 (`archive/avo-solver/`); its campaigns
stay readable but cannot be resumed.

## Outer evolution

Each `x_i` is one complete strategy plus inherited workspace seed. The outer optimizer:

1. designs `x_0001` from a frozen initial observation without gameplay access;
2. evaluates `x_i` by its research session in a fresh environment;
3. inspects any page of its research transition history;
4. forks the final workspace (notes, `world_model.md`, scripts) into `x_(i+1)`;
5. changes the next strategy or seed;
6. continues until success or the configured outer evaluation limit.

An unsuccessful `x_i` remains part of the lineage. It does not trigger a replacement
top-level `v2` or `v3` run.

## Authority and safety

- Only the environment profile determines progress, success, and terminal state.
- Codex cannot edit trusted evidence or execute environment actions outside the gateway.
- Checkpoint identifiers are opaque and reveal no hidden state.
- Registered outer candidates and evaluation records are framework-owned.
