# Rule-learning curves (28 Oct 2026)

How much of each game's true rules the player's `world_model.md` states, as play goes on.

- `curves.json`: per run, every rebuilt version of `world_model.md` with its counters (minutes, generated and
  processed tokens, tool calls, game actions, levels) and, for the graded versions, one label per rule
  (correct, partial, wrong, absent). Level-ups and run totals are included.
- `rules.json`: the true rules per game, written from each game's `script.txt` and tagged visible or hidden.
- `rule-learning-all.png`, `-hidden.png`, `-visible.png`: score (correct = 1, partial = 0.5) against game
  actions, tool calls and generated tokens, for the agent-driven Harness² base run and the controller-driven
  baseline v4 run of each game.
- Scripts, run from a scratch folder: `rebuild.py` replays the write and edit events in each run's `raw/`
  (falls back on `world_model_snapshots/` when the replay is incomplete), `prepare.py` samples at most 12
  versions per run for grading, `plot.py` draws the figures.

Runs: the 8 controller-driven baseline runs and the 3 agent-driven Harness² base rollouts of 21 Oct
(`output/workbench/20261021T14450*`, `20261021T151117*`, `20261021T155237*`, `20261021T162323*`).
Grading: five Claude subagents (split by game), each version graded on its own without the run name; not yet
checked by hand.

## Combined grade: notebook + thinking (1 Nov 2026)

The per-game figures (`rule-learning-{modality,icecrates,knightoban}.png`, `rule-learning.html`) now show what the
model believes, read from its notebook and its thinking trace. The earlier notebook-only line is drawn faint and
dashed in the same colour. Only the six runs of 21 Oct are covered: one agent-driven and one turn-based run
(baseline v4) per game.

- Checkpoints: every 25 game moves, every level completion, every distinct `world_model.md` version (all of
  them, no 12-version cap), and the run end. A window holding more than 100k characters of thinking gets extra
  checkpoints inside it. That gives 208 checkpoints.
- At each checkpoint a grader read the latest notebook and all the thinking (`"type":"reasoning"` events in
  `raw/turn-*.jsonl`) since the previous checkpoint, with the previous labels as context. It labelled every rule
  correct / partial / wrong / absent. Only stated beliefs count: a "maybe" or a "what if" does not. A belief holds
  until the model contradicts or drops it. Each label records its source (`notebook`, `thinking`, `both`) and the
  label the notebook alone earns at that moment. The rubric is in `grade/INSTRUCTIONS.md`.
- Graders: Claude subagents (Opus 5.5), one per segment of about 280k characters, 29 segments run in sequence
  within each run. Runs were renamed A–F, so graders saw neither run names nor the driver (key in
  `grade/key.json`). Total: 1,554 labels.
- `curves-combined.json`: per run, every checkpoint with its counters, the combined labels, the sources, the
  notebook-only labels, the graders' evidence notes and both scores. It also holds the old notebook-only curve
  (`old_notebook_curve`, from `curves.json`).
- Scripts, run from the repo root: `checkpoints.py` builds the checkpoints and the blind grading folders
  (`grade/run-*/seg-*/cp-*.md`, 6.8 MB, regenerable). `grade/ready.py` hands each segment's final labels to the
  next segment. `grade/check.py` validates a segment. `combine.py` joins the labels into
  `curves-combined.json`. `figures.py` draws the HTML and the PNGs with headless Chrome.

Hand spot-check: 23 labels read against the text. Every evidence quote is real text: 71 match word for word by
script, 3 more by eye after reformatting, and the other notes explain an `absent`. 18 labels agree and 2 are
borderline. 3 are grader errors:
- Turn-based IceCrates, rule I5 (water blocks the player), moves 0–43: the grader read the walls of levels 1–3
  ("pit", "rimmed dark blockers") as water. Fixed in `combine.py` (`CORRECTIONS`); the raw labels stay in
  `grade/`.
- Agent-driven Modality, rule M5: "checker is decorative" was graded wrong. I would grade it absent. Both score 0.
- Agent-driven Knightoban, rule K7: "a level ends when no bright rings remain" was graded partial. I would grade
  it correct; the old notebook grade said correct.

The pattern: graders are a little strict on correct vs partial when the model states the rule from another angle.
They can also map an object to the wrong rule when an early object looks like a later one.

What changed:
- Modality, agent-driven: 50% at move 71, not 19% until move 700. The jump at 71 is the notebook version the old
  12-version sample skipped. The thinking then adds 6–19 points (56% at move 101, 62% at 252, 69% at 656) before
  the notebook catches up at 700. It ends at 69%, as before. Turn-based is still ahead (88–94%).
- IceCrates: both lines rise earlier. Turn-based reaches 71% by move 46, where the notebook showed 43% until
  move 160. Agent-driven reaches 100% at move 269, then ends at 93% after a notebook rewrite with a wrong
  "rotor" rule for water.
- Knightoban, agent-driven: 71–79% by moves 78–101, before the first win at 109. The notebook stayed at 57%
  until move 326. It ends at 79%, not 86% (the stricter K7). Turn-based: 21–36% from move 9, then 43% from move 100 to the end.
  The table now shows ✗ for the win rule: the model said the goal is not "ring on ball".
