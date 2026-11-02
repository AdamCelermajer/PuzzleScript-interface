# Thinking trace vs notebook: how the rule-learning curves would change (1 Nov 2026)

Question: if we graded rule learning from the model's thinking instead of from its `world_model.md` versions,
how would the curves in `rule-learning-{modality,icecrates,knightoban}.png` change?

This is a heuristic estimate, not a grade. I searched the thinking text with keyword patterns, read the matched
passages, and picked the first move where the model states a rule as its working belief. No LLM was called.
The numbers below are a guide for where a proper grading pass would move the curves.

## Short answer

- The thinking runs ahead of the notebook in every agent-driven run. The notebook lags because the agent
  rewrites it rarely (Modality: moves 71 → 700; Knightoban: moves 22 → 326).
- The final level of each curve barely changes. The model does not know more than it writes down; it writes it
  down later.
- The flat 19% line of the agent-driven Modality run is partly a sampling artifact. The notebook version written
  at move 71 was never graded. That version already describes Sokoban pushing, the push rule and a win
  hypothesis. I estimate it at about 50%, not 19%.
- Thinking-based grading would lift agent-driven Modality to about 62% by move 85, the level the notebook only
  shows at move 700. After that it stays flat. The model is stuck on a wrong idea ("hidden walls between
  cells"), not on a stale notebook.
- Turn-based runs change less, because their notebook is updated often. Thinking still moves IceCrates and
  Knightoban 50–120 moves earlier, where the notebook has gaps.
- The agent-vs-turn conclusions hold. Agent-driven is still ahead in IceCrates and Knightoban. Turn-based is still
  ahead in Modality, but the gap shrinks from about 55 points to about 15–25 points over most of the run.

## Method

- Thinking: every `"type":"reasoning"` event in `raw/turn-*.jsonl` (`part.text`, `timestamp` in ms UTC).
- Move index: bisect the thinking timestamp into the `transitions.jsonl` move timestamps. "Move N" means the
  model had seen N moves when it wrote that thought. In agent-driven runs one tool call can play many moves, so
  the move index is coarse there.
- Belief: a rule stated as the model's working model ("So the orange tile is a pushable box"), not a passing
  "what if". Confirmed: stated after the model saw it work, or written as "verified/confirmed".
- Notebook: first graded version in `curves.json` where the rule is partial (p) or correct (c). `w` = graded
  wrong, `a` = absent.
- Score estimate: same weights as the plots (correct 1, partial 0.5), using my reading of the thinking.

## Modality

| Rule | Agent: thinking | Agent: notebook | Turn: thinking | Turn: notebook |
|---|---|---|---|---|
| M1 controls | c at 0 (only moves + undo offered) | c at 46 | p (wrong idea: ACTION7 "launches" the player, 10–16) | p at 25, stays p |
| M2 push | c at 71 ("pushable box, like Sokoban") | w at 46, c at 700 | c by 25 (level 1 solved by a push) | c at 25 |
| M3 refused push | p at 71 (off grid / into wall) | p at 700, c at 1000 | c by 25 | c at 25 |
| M4 colour blocks player | p at 32 as "hidden wall between cells"; many walls at 43 | p at 46 | c at 21 ("can't cross from black to white") | c at 25 |
| M5 grey connects | absent ("checker is decoration") | absent | c at 21 ("checkerboard is the only door, both ways") | c at 25 |
| M6 push depends on floor | p at 85 (failed push → "probably a wall"); same walls for box and player at 252 | p at 700 | doubts only, around 60–75 | p at 71 |
| M7 crate ignores colour | p at 78 ("8 = box on dark floor") | p at 700 | p by 25 | p at 25, c at 60 |
| M8 win | hypothesis at 71, c at 78 (level 1 won) | c at 700 | c by 25 | c at 25 |

Wrong beliefs:
- Agent: "hidden walls between adjacent cells" from move 32 to the end. At move 311 it checks the floor colour
  of failed pushes, finds no pattern, and keeps the walls. Also "orange tile blocks" (35–70), dropped at 71.
- Turn: "ACTION7 on the checkerboard launches the player" (10–16). It is the undo. Partly dropped at 16,
  where it calls ACTION7 a step-back, but it never states plain undo.

Estimated score, agent-driven: 19% up to move 70, 44% at 71, 56% at 78, 62% at 85, then flat (69% at the end).
The notebook graph shows 19% until 700. The ungraded notebook version at move 71 (identical to snapshots
a0100–a0600) would score about 50% by my reading: M1, M2, M3 correct, M4 and M8 partial.

Estimated score, turn-based: same as the notebook within a few moves (75% from about 21–25, 81–88% later).

## IceCrates

| Rule | Agent: thinking | Agent: notebook | Turn: thinking | Turn: notebook |
|---|---|---|---|---|
| I1 controls | c at 2 | p at 0, c at 15 | c early (wrong idea at 27: ACTION7 = "180° turn") | c at 7 |
| I2 slide | hypothesis at 2, c at 9 | c at 15 | belief at 1 | p at 7, c at 9 |
| I3 push while sliding | c at 18 (box carried ahead, both stop) | c at 31 | hypothesis at 1, "verified" for moves 33–37 | a at 9, c at 160 |
| I4 chain push | belief at 207 (two boxes moved together) | a until 144, c at 300 | w at 83–94 ("no chain push") | w at 160 |
| I5 water blocks player | p at 47 ("door blocks the creature in all 5 states"), mixed with a wrong rotor idea | w at 106, p at 300, w at 320 | p at 38–42 (blue object blocks), then "state 27 passable" at 47 | w at 160 |
| I6 crate fills water | c at 56 (box absorbed, door passable) | c at 106 | c at 46–47 (crate vanished, blue now passable) | p at 160 |
| I7 stop on goal | open question at 10 | p at 15, c at 31 | belief at 9–12, "verified on L1, L2" at 45 | w at 7, c at 9 |

Wrong beliefs:
- Agent: calls the ice "water" (from move 9; the final notebook still says "6 — water, the common passable
  ground"). Reads the water animation (IDs 22–26) as a "5-state rotor" that blocks by direction. Both kept to
  the end.
- Turn: "no chain push" (83–94), kept. "ACTION7 = 180° turn" (27).

Estimated score, agent-driven: 50% at 18, 71% at 56, 86–93% from about 207. The notebook reaches 71% at 106 and
93% at 300. So the curve moves 50–100 moves earlier, with the same top.

Estimated score, turn-based: 43% at 12, 57% at 37, 64–71% from 47. The notebook stays at 43% from 9 to 160 and
reaches 64% at 160. The notebook has no version between moves 9 and 100, and the version at 100 was not graded.
So the curve moves about 110 moves earlier, with the same top.

## Knightoban

| Rule | Agent: thinking | Agent: notebook | Turn: thinking | Turn: notebook |
|---|---|---|---|---|
| K1 controls | c at 17 (ACTION5 = confirm) | p at 1, c at 22 | p ("ACTION5 = wait" at 58) | p at 100 |
| K2 walls, orange crates | no clear statement found | p at 326 | no clear statement found | p at 100 |
| K3 knight jump | p by 22; c at 74–78 (2 ahead, 1 to the side, two landing ends) | p at 22, c at 326 | p at 28 ("2 squares + 1 at 90° clockwise") | p at 100 |
| K4 landing must be free | p at 78 (no landing on a wall), c-ish at 215 (blocked ends not offered) | p at 326 | not found | p at 100 |
| K5 keys switch landing | observed at 11, belief by 17 | c at 22 | not found (dashed cell read as a "shadow") | p at 100, w at 300 |
| K6 ACTION5 confirms | c at 17 | c at 22 | p at 58 ("wait" lets the ring land) | p at 100 |
| K7 win | hypothesis at 13–17 (ring on socket), c at 109 (level won) | p at 22, c at 326 | not found | absent |

Wrong beliefs:
- Agent: early "pick up / ball" ideas, dropped by 17. No lasting wrong rule found.
- Turn: the jump goes only "90° clockwise", a fixed landing. Never replaced by the choice rule. Early "carry the
  ball" ideas (9–13), dropped.

Estimated score, agent-driven: about 50–57% at 22, 71% at 78, 79% at 109, 86% from about 215. The notebook
stays at 57% from 22 to 326 (no rewrite in between) and then jumps to 86%. So the curve moves 100–250 moves
earlier, with the same top.

Estimated score, turn-based: about 30–43% from moves 28–58. The notebook exists only every 100 moves (snapshots)
and shows 43% from move 100. So the curve starts about 50 moves earlier; its top stays near 43%.

## What changes in the comparison

| Game | Notebook graph says | Thinking graph would say |
|---|---|---|
| Modality | Turn learns fast (75% at 25); agent stalls at 19% until 700 | Agent learns the visible rules fast too (62% by 85) but builds a wrong model of the hidden rule; turn still ahead by about 15–25 points |
| IceCrates | Agent ahead late (93% vs 64%) | Same order; both curves rise 50–110 moves earlier |
| Knightoban | Agent ahead (86% vs 43%); agent flat 22–326 | Same order; the agent's rise comes before its first win at 109, not at 326 |

The main effect is on timing. Thinking-based curves rise earlier and look smoother. The final level stays put.
In both agent-driven runs with big gaps (Modality, Knightoban), the notebook was not rewritten while the model
was learning.

## Two problems with the current graphs found on the way

- Sampling: `prepare.py` grades at most 12 versions per run. In agent-driven Modality it skipped version 3, the
  move-71 rewrite. That is why the line sits at 19% until 700. In turn-based IceCrates it skipped the version at
  move 100, which hides part of the rise. In turn-based Modality it skipped six versions (moves 39, 75, 100, 112,
  159, 200).
- Sparse notebooks: turn-based Knightoban has only the snapshots at 100, 200, 300, 400. Turn-based IceCrates has
  no version between moves 9 and 100.

Grading all versions would fix the first problem without any change of method.

## Where an LLM grader is needed

- Belief vs guess. The thinking is full of "what if" lines. Keywords cannot tell a belief from a guess; I did
  that by reading, and only for the first hits.
- The model's own words. It calls things "door", "ring", "socket", "cage", "bar", "rotor" and "hidden wall".
  Matching these to the true rules needs reading. Example: the IceCrates "door" is the water.
- Partial vs correct, especially for M4/M6 (hidden walls vs floor colour), I5 (blocks, but with a wrong rotor
  rule) and K3/K4 (how much of the jump rule is stated).
- Rules I could not find with keywords: K2 in both Knightoban runs, K4–K5 and K7 in turn-based Knightoban, M6
  in turn-based Modality.
- Whether a wrong belief was dropped. That needs reading the later thinking, not only the first hit.
- Every rule after its first hit. I did not check whether a belief was later doubted or replaced.

## Thinking volume (for a later paid grading pass)

| Run | Moves | Reasoning parts | Thinking chars | Approx. tokens (chars/4 to chars/3) | Generated tokens (curves.json) |
|---|---|---|---|---|---|
| Modality agent | 1000 | 327 | 1,552k | 390k–520k | 784k |
| IceCrates agent | 320 | 197 | 1,615k | 400k–540k | 673k |
| Knightoban agent | 326 | 196 | 667k | 170k–220k | 292k |
| Modality turn | 226 | 265 | 741k | 185k–250k | 365k |
| IceCrates turn | 271 | 335 | 675k | 170k–225k | 337k |
| Knightoban turn | 451 | 501 | 697k | 175k–230k | 318k |
| Total | | 1,821 | 5,947k | 1.5M–2.0M | 2.77M |

The chars-per-token range is a guess. Coordinates and digits tokenise densely, so the true count is probably
nearer the upper end. One grading pass that reads all the thinking once, in move-ordered chunks with the rule
list and a running belief state, needs about 2–2.5M input tokens over the 6 runs. Output is small. Grading only
the chunks around notebook gaps (Modality agent 71–700, Knightoban agent 22–326, IceCrates turn 9–160) would cut
that to roughly a third.

Scripts used (scratch, not in the repo): `C:\Users\adamc\AppData\Local\Temp\tvn\dump.py` writes each run's
thinking with move indices; `g.py` and `g2.py` search it.
