# Experiment plan: one change at a time (draft, 2026-10-20)

Yoav's point (20 Oct): the Harness² agent run on Modality looked better than Baseline+
and AVO, but it changed several things at once: who drives the game, the task, the
CLI, the provider, the effort and image input. Nothing can be attributed. This plan
fixes everything except one factor per experiment.

## What differed in the runs we have (Qwen 3.8 27B, Modality)

| run | who drives the game | task | CLI | provider / variant | effort | image | budget |
|---|---|---|---|---|---|---|---|
| Baseline+ 8 Oct | our controller, one action per call | levels during play | Codex | OpenRouter 27B | high | sent by Codex | 100 |
| Baseline+ 15 Oct | our controller | levels during play | Codex | NanoGPT 27B-thinking | high | sent by Codex | 1000 |
| AVO 13 Oct | the agent, `avo_tool.py` | build `solver.py` (play is research only) | Codex | OpenRouter 27B | high | ? | 234 research, 1500 solver |
| Harness² old player | our controller | levels during play | OpenCode | NanoGPT 27B-thinking | medium | yes | 200 |
| Harness² agent player | the agent, `game.py` | levels during play | OpenCode | NanoGPT 27B-thinking | medium | yes | 200 |

Only the last two rows differ in one factor (who drives the game). Every other pair
differs in two to five.

## Factors

| factor | values |
|---|---|
| A. who drives the game | controller (one action per call) · agent (`game.py` in a persistent folder) |
| B. memory | none · notes required (Baseline+ style) |
| C. CLI | OpenCode · Codex · bare (pending `opencode-vs-codex-20261020.md`) |
| D. outer method | none · Harness² · AVO |
| E. task | levels during play · solver from a fresh start |

## Held fixed in every experiment

- Model: Qwen 3.8 27B, one provider and one variant (to choose; today NanoGPT
  `qwen3.8-27b:thinking` is the only 27B route that works with images).
- Effort: one level for all runs.
- Image input on, recorded in `session.json`.
- Budget: the same number of game actions per run; wall time unlimited.
- Games: one fixed set across experiments (proposal: 4–6 games over the easy/medium/hard
  tiers of `benchmark/games.json`, Modality included).
- Repeats: 3 per cell (one run per cell is what made today's comparisons anecdotal).
- Scoring: levels completed during play, the action at which each level was completed,
  and the end-of-run world model checked against each game's real rules.

## Ladder

1. **Who drives the game (A × B).** Controller vs agent, notes off vs on. CLI OpenCode,
   no outer method, task = levels during play. Four cells.
2. **CLI (C).** The best cell of step 1 under OpenCode vs Codex (and bare), if Codex can
   run Qwen 27B with the same provider.
3. **Outer method (D).** The best player of steps 1–2 alone vs inside Harness², same task
   and budget per player run. Harness²'s base rollout must then be exactly that player.
4. **Task (E).** Separately: levels during play vs solver from a fresh start, the one
   difference between AVO's task and the others. Only then is AVO comparable.

## Code

- Done (20 Oct): Baseline has a `driver` option, `controller` (`run.py`) or `agent`
  (`agent.py`, the `game.py` player). Harness² runs `agent.py` with notes off, so its base
  rollout is exactly "Baseline, driver agent". Step 1 is the four Baseline variants:
  Baseline, Baseline · agent, Baseline+, Baseline+ · agent.
- Decided (20 Oct): Modality only first, one run per cell for now.
- Every run records all factors (A–E plus provider, variant, effort, image, budget) in
  `run_spec.json`, so the catalog can group runs by the factor that differs.
