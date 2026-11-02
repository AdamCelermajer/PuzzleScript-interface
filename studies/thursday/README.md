# Thursday analysis (22 Oct 2026): Modality runs

Analysis scripts for the Modality experiments (`docs/research/thursday-experiments-20261020.md`).
They read run folders and write to `output/thursday/` (gitignored). A run folder is any folder with
`transitions.jsonl`: a Baseline run (agent or controller driver) or a Harness² rollout
(`.../rollouts/base1`). Give a job or Harness² run folder and the run folders below it are found.

Run from the repository root with the project venv (`uv run python -m ...` or `.venv/Scripts/python -m ...`).

| script | what it does | example |
|---|---|---|
| `modality.py` | The game's true rules, the shortest solution of each level (BFS: 6 / 33 / 66 / 158 moves, so 105 for levels 1–3 and 263 for all four), and `replay(actions)`, the true state after every action (undo, RESET and level loading as the runtime does them). Without arguments it validates the replay against the 20 Oct Harness² rollouts. It checks every action: changed flag, levels completed, and the exact cells that changed. | `python -m studies.thursday.modality [RUN ...]` |
| `metrics.py` | One row per run, then one row per arm. Each run row has: <br>• the action at which each level was completed; <br>• extra moves per level over the optimum; <br>• moves to finish levels 1–3; <br>• blocked moves per level, by cause: white↔dark step, wrong-floor push, board edge; <br>• undo count, agent turns, play and session minutes; <br>• tokens and cost at NanoGPT prices; <br>• errors and harness counters (`COUNTERS`, e.g. tool calls returned as text). <br>Writes `runs.csv`, `arms.csv`, `runs.md`. | `python -m studies.thursday.metrics output/workbench/<job> --label '*/rollouts/base1=plain' --label '*/rollouts/*=flash coach'` |
| `curves.py` | Levels completed against actions used: one panel per arm, one line per run, the optimum dashed. | `python -m studies.thursday.curves output/workbench/<job> --label ... --out output/thursday/curves.png` |
| `solver_eval.py` | Plays a run's end-of-run `solver.py` against the real game, level by level. For each level, a fresh session first replays the run's own actions up to that level, so the tile ids match what the run saw (`ids match` column). The solver then runs in its own process with a per-call timeout. A level the run never reached is reached through the optimal solutions of the levels before it (`run+optimal`). Needs the local game service (`npm run local`); never starts or restarts it. | `python -m studies.thursday.solver_eval RUN [...] --levels 1 2 3 4 --max-steps 300` |
| `rules_timeline.py` | Candidate statements of the 7 rules in reasoning and messages, each with the number of game actions taken at that moment. The rules are: action map, undo, white↔dark blocked, grey bridge, push, matching-floor push, goal. Writes `candidates.csv`, with an empty `label` column for labelling (correct / wrong / guess), and `first_mentions.md`. Matching is loose, so first mentions are upper bounds, not verified statements. | `python -m studies.thursday.rules_timeline output/workbench/<job>` |

Arm labels default to the run's configuration (harness, model, driver, `notes`, `start` folder), or
`h2 <label>` for Harness² rollouts; `--label 'GLOB=ARM'` (fnmatch on the run path, first match
wins) overrides them. Prices live in `metrics.PRICES`. The `qwen3.8-flash` cached price is unknown,
so cached Flash tokens are billed as fresh input.
