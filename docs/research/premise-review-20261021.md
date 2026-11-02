# Premise review: does Qwen 3.8 27B fail at learning PuzzleScript games? (21 Oct 2026, 17:15)

Read-only review. Runs still live at the time of writing: Baseline v4, AVO v2, Harness² coaching. Numbers
below are from the run folders cited; per-level move splits come from `studies/thursday/premise_moves.py`.

## 1. The premise and what supported it

**Premise** (memory `qwen-harness-research-direction`, `docs/research/qwen-harness-direction.md`, 4 Oct):
"Qwen 3.8 27B fails the PuzzleScript games; find out whether the cause is the harness, its size or its
pretraining." Smaller non-Qwen models (DeepSeek V4.1 Flash, GPT-6 Luna) solved the same games.

**The evidence, re-read:**

| when | setup | outcome | real cause |
|---|---|---|---|
| 30 Sep – 1 Oct | AVO and Baseline+ via Codex, OpenRouter | runs died or were stopped | Docker down, transport resets, the guard rejecting Codex's own `get_goal` tools, prose before JSON ending the run. **Infrastructure.** |
| 30 Sep – 1 Oct | Baseline+ turn by turn, ≤124 actions | Modality level 1, then stalled on level 2 | partly real: `qwen27b-modality-failure-analysis.md` found poor hypothesis revision (never found undo or pushing). Also a turn-by-turn setup with ≤124 actions. |
| 8 Oct | pinned to DeepInfra | every run ended at exactly 30 actions | "Too many images in request: 31 > 30". **Infrastructure.** |
| 15 Oct | Codex on NanoGPT | 11 of 25 tool calls came back as text | NanoGPT drops Codex's namespaced tools (`thursday-20261022.md` §2). **Infrastructure.** |
| 20 Oct | Harness² on NanoGPT, the 27B driving the game, Flash as coach | all 5 games reached Modality level 3; level 4 out of reach | the 200-move budget: all 4 levels need at least 263 moves (§3 of the Thursday notes). **Budget.** |
| 21 Oct, 13:00 | quantization runs (NanoGPT pinned hosts, agent-driven, Modality) | 1–2 levels in 59–235 moves | stopped by hand at about 35 min. **Time limit.** (`output/workbench/20261021T130008-thu-quant-*`: 16-bit 2/2/2 levels, 8-bit 1/2/1, 4-bit 2/1/1) |
| 21 Oct, vast server | Baseline v1–v3, AVO v1 | stopped, stalled or crashed | turn-protocol bugs (action and note in one message; a note loop), AVO's 40k-character raw-JSON move output with a stale first board, the OpenCode context crash. **Infrastructure**, fixed during the day. |

So nearly every recorded "failure" was infrastructure, budget or time. The one real capability finding,
poor hypothesis revision on Modality, came from a 124-action, turn-by-turn setup.

## 2. What happened today, and why it worked

Setup: Qwen 3.8 27B, official 8-bit weights, 8-bit context cache, self-hosted vLLM, max thinking, OpenCode,
no wall-clock limit, 1000 moves per attempt.

### Harness² first attempts (base1: the agent-driven Baseline with an empty harness)

Run folder `output/workbench/20261021T144508-vast-fp8-harness2-153a4dc2/run-000{1,2,3}/rollouts/base1`.

| game | result | moves per level | reference shortest per level |
|---|---|---|---|
| Knightoban | **6/6, 326 moves** | 109 / 55 / 62 / 41 / 31 / 28 | 20 / 10 / 33 / 41 / 32 / 28 (BFS counting steps and jumps, `studies/thursday/rules/knightoban.md`) |
| IceCrates | **6/6, 320 moves** | 10 / 5 / 16 / 113 / 144 / 32 | 4 / 5 / 12 / 29 / 8 / 32 (`studies/thursday/rules/icecrates.md`) |
| Modality | 3/4, 977+ moves (still running) | 78 / 96 / 230 / 581+ | 6 / 33 / 66 / 158 |

**How it solved: a correct model plus its own search.**
- In every game it wrote a breadth-first solver over its own model of the rules and played the plans
  it produced.
  - Knightoban: `bfs*.py` and `bfs_l2*.py`, then `exec_l4.py`, `exec_l5.py` and `exec_l6.py`.
  - IceCrates: `l4_bfs*.py`, `l5_bfs.py`, `l6_bfs.py`, then `runseq.py`.
  - Modality: `plan.py` and `search.py`.
- Nearly all moves came from scripts or action lists rather than one `do` at a time (premise_moves.py).
  Knightoban levels 4–6 were each played in a single scripted run.
- **Where the model was right, play was optimal or near optimal.**
  - Knightoban levels 4–6: 41/31/28 against the reference 41/32/28.
  - IceCrates levels 2 and 6: 5 and 32, both equal to the shortest.
- **The exploration cost sits in the first levels and in the levels where its model was wrong.**
  - Knightoban level 1: 109 moves against 20, to learn the knight jump.
  - IceCrates levels 4–5: 113 and 144 moves against 29 and 8. It was stuck against water it believed
    passable, then spent about 60 moves in a state that could no longer be won
    (`output/thursday/vast/watch/h2-icecrates-1635.md`).
- **Where the model was wrong, the search failed.**
  - Modality: it never found the floor-colour rule.
  - It encoded white–dark boundaries as 49 per-edge "walls", and its planner found no path on level 4
    (`h2-modality-1635.md`). Search amplifies understanding in both directions.

### Rules learned (grader reports in `output/thursday/vast/watch/`)

- **Knightoban:** all 7 real mechanics held at the end, the last by move 109.
  - One wrong rule: "undo cannot revert a portal entry".
  - The coach then copied that wrong rule into the harness.
- **IceCrates:** 6 of 9 held, including in practice.
  - Wrong: water is passable vertically, water acts as a gate.
  - Wrong notes: tile 6 is water; "moving onto the plant wins".
- **Modality:** 4 of 7 held: controls, undo, pushing, goal.
  - Never found: rule 3 (no white–dark step), rule 4 (grey connects) and rule 6 (pushes need matching floors).
  - These are the hidden floor-colour rules.

### Other frameworks today (live, at 17:12)

- **Turn-based Baseline v4** (`…/20261021T162323-vast-fp8-baseline-v4-6767db38`), after about 50 min:
  - Modality 2/4 in 111 moves;
  - IceCrates 3/6 in 46;
  - Knightoban 0/6 in 67.
  - Earlier turn-based versions were cut short by protocol bugs. v1 IceCrates had 3/6 in 46 moves.
- **AVO v2** (`…/20261021T160936-vast-fp8-avo-v2-b994ed09`), first attempt still researching:
  - Modality 2/4 in 93 research moves;
  - IceCrates 4/6 in 84;
  - Knightoban 1/6 in 257.
  - No attempt has been scored yet.

## 3. What the 27B learns and what it doesn't

- **Learns:** the controls, undo, the visible results of actions and pushing, and goals it can see happen.
  - It learns these within tens of moves.
  - It also writes working simulators and solvers for those rules.
- **Doesn't learn:** a rule that leaves no visible trace. In Modality, a step or push is refused depending
  on the floor colour, and it reads every refusal as a local wall. It doesn't revise into a general rule,
  even after more than 100 blocked moves.
- **Holds wrong beliefs** that its own play never contradicted:
  - Knightoban: undo.
  - IceCrates: water, and the plant.
- **Does not keep `world_model.md` current.**
  - IceCrates' file was last written at move 13.
  - Modality's snapshot was stale.
  - The knowledge lives in the reasoning and in its scripts.
  - Grading must use the reasoning.

## 4. Implications

**"The 27B fails" is no longer true as a general statement.** With working tools, a 1000-move budget and the
freedom to write and run its own search, it solved 2 of 3 games in its first attempt.

The candidate reframings, with the evidence for each:

1. **The earlier failures were mostly infrastructure, budget and time.** Strongly supported (§1).
2. **It succeeds when it can write and run its own search** (agent-driven with tools). Supported:
   - All three base1 games relied on its own BFS.
   - Turn-based play is much slower: v4 has 0–3 levels after about 50 min, where base1 had Knightoban
     solved in about 60 min.
   - This is not yet separated from budget and pace. Turn-based v4 also has tools, but it cannot run a
     plan in one call.
3. **The hard part is hidden rules, not visible mechanics.** Supported by Modality across every setup:
   20 Oct, the quantization runs and today all stall at the floor-colour rule.
4. **The games are easy or leaked.**
   - All three are public PuzzleScript games: Modality by Sean Barrett, IceCrates by Tyler Glaiel,
     Knightoban by Nick Sperry.
   - Knightoban's levels 2–6 are the public Microban 1/5/6/7/13 layouts.
   - Our prompts omit titles and tiles are anonymous IDs.
   - In base1's reasoning, no title, "Microban", author or even "knight" appears (it called the pieces
     "rings" and "sockets"). Only "Sokoban" appears, as a genre analogy (43/8/3 mentions).
   - So there is no sign of recall, but exposure to the layouts can't be ruled out. The levels it
     solved fastest were the late Knightoban ones, after it had built a solver.

**Cheap experiments that separate these:**

| question | experiment | cost |
|---|---|---|
| search vs understanding | agent-driven, but Python execution blocked (shell for notes only); one run per game, 300 moves | 3 runs |
| turn-based vs agent-driven at equal budget | already running: Baseline v4 against base1, same server and budget | 0 |
| hidden rule is the bottleneck | Modality with one true note ("a step or push between white and dark floor is refused; grey connects"): does level 4 fall? | 1–3 runs |
| memorised layouts | the same rules on transformed levels (mirrored or rotated Knightoban/Microban maps, or new layouts); compare moves per level | 3 runs plus a level edit |
| recall | ask the 27B, with no game, about "Knightoban", "Microban 5" and "Modality PuzzleScript" | minutes |
| size | the same agent-driven setup with Qwen 3.8 Flash and Max | 3–6 runs |

## 5. Conclusion for Thursday

- With working infrastructure, Qwen 3.8 27B (8-bit, self-hosted) solved Knightoban (6/6, 326 moves) and
  IceCrates (6/6, 320) in its first agent-driven attempt, and reached 3 of 4 levels in Modality.
- Most earlier failures were tool, protocol, budget and time limits, not the model.
- It succeeds by inferring visible mechanics, encoding them in its own breadth-first solver, and playing
  the plans, at or near the shortest length once its model is right.
- It fails where a rule leaves no visible trace (Modality's floor colours). There a wrong model makes its
  own search fail, and it keeps a few wrong beliefs it never tests.
- The research question should move from "why does the 27B fail" to "under which conditions does it learn
  a game, and how does it revise a hidden rule". The cheap ablations in §4 test that.
- Limits: one attempt per game; public games with public Microban layouts; graders are LLMs checked
  against verified rule lists.
