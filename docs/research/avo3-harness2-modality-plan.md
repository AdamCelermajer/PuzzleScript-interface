# Plan: AVO3 and Harness² Modality per level (21 Oct 2026, evening)

Planning only: no code changed, nothing launched. Both runs go on **OpenRouter with OpenCode**, not on the vast
instance (Adam, 21 Oct).

## 0. OpenRouter setup, shared by both runs

### Model and host
- **Model id:** `openrouter/qwen/qwen3.8-27b`. This is snapshot `qwen3.8-27b-20260814`, the same weights as today's
  self-hosted `Qwen3.8-27B-FP8`: Hugging Face weights unchanged since 13 Aug.
- **Pin one host, fallbacks off.** Our harness already supports this: the run spec's `provider` field becomes
  `{"provider": {"order": [host], "allow_fallbacks": false}}` in the request body (`harnesses/opencode.py`,
  `opencode_config`). That's the body-level pin, which OpenRouter honours, not the NanoGPT header that fell back.
- **Hosts and their limits** (OpenRouter endpoint list, 21 Oct evening; prices per M tokens):

  | Host | Precision | Context | Max answer | Input | Cached input | Output | Implicit caching |
  |---|---|---|---|---|---|---|---|
  | Chutes | fp8 | 262,144 | 65,536 | $0.039 | $0.0039 | $1.25 | yes |
  | Near AI | fp8 | 262,144 | 65,536 | $0.04 | $0.018 | $1.35 | yes |
  | Ionstream | fp8 | 262,144 | 65,536 | $0.04 | $0.02 | $1.95 | yes |
  | Parasail | fp8 | 262,144 | 235,929 | $0.24 | $0.05 | $2.20 | yes |
  | CoreWeave | fp8 | 262,144 | 235,929 | $0.40 | $0.15 | $3.00 | yes |
  | DeepInfra | bf16 | 262,144 | 235,929 | $0.15 | $0.0375 | $1.875 | yes |

  - Q2 showed that precision matters, and the 8-bit server matched today's results, so an **fp8 host** keeps the
    comparison with today.
  - **Chutes and Near AI** are the cheapest fp8 hosts. Both cap one answer at 65,536 tokens, which is just above our
    64k answer reserve.
  - Today's "OpenRouter est." column used Near AI's prices. Chutes is about 7% cheaper on output, and 4–5× cheaper
    on cached input.
  - All of them except Mancer and Venice do **implicit prompt caching**. That matters because most of our input is a
    resent conversation (92% cache hits on our server today).
  - **Image caps:** DeepInfra refused more than 30 images per request on 8 Oct. That no longer matters for us: the
    turn-based Baseline now passes the frame only as a path, the agent-driven players open `frame.png` with their read
    tool, and AVO prints a grid. One open check: whether each `read` of an image stays in the conversation.
  - **Rate limits:** OpenRouter has no per-model cap on paid credit, but each host can return 429 under load. Our
    sessions retry 429/502/503 with backoff (`TRANSIENT` in `frameworks/baseline/session.py`). AVO's and Harness²'s
    retries go through the same harness. Not measured: Chutes under 6–9 parallel long sessions.

### OpenCode settings for an OpenRouter model: one required change
- **Context limit: required code change.**
  - OpenCode takes model limits from models.dev, which lists `openrouter/qwen/qwen3.8-27b` with a **1,000,000-token
    context**: the 1M figure comes from the Alibaba, Novita and Phala endpoints. With that, OpenCode would compact
    only near ~936k.
  - A pinned 262k host would reject the request first, so every long session would die at 262k with no compaction.
    That's the context crash, every time.
  - Fix: declare `limit: {context: 262144, output: 64000}` for OpenRouter models in `opencode_config`, as the vast
    provider already does. Compaction then happens at about 198k, as today.
- **Answer cap:** keep 64,000 (`OUTPUT_TOKEN_MAX`). Chutes and Near AI can't go above 65,536 anyway.
- **Thinking:** effort `max` maps to OpenRouter `reasoning_effort: xhigh` (`VARIANT` in `harnesses/opencode.py`),
  the same as today.
- **Sampling differs from today:** OpenCode sends temperature 0.55 / top_p 1 for model ids containing "qwen", while
  our vast server ran the model's own 1.0 / 0.95 / top_k 20 (the served name had no "qwen" on purpose). Matching
  today needs a small code change: per-model `temperature`, `top_p` and `top_k` options in `opencode_config`.
  Otherwise, record it as a difference from today.
- **Still open, edge case:** compaction ignores thinking tokens, so one very long thinking step can still overflow
  (today: 1 run killed, 6 recovered). AVO is the most exposed (section A4).

## A. AVO3: research budget growing per attempt

### A1. What to change in `frameworks/avo/`
The research budget is set once per campaign:
- `research_moves` (`framework.py`) → `--player-max-environment-steps` (`evolve.py`) →
  `PlayerRunSettings.max_environment_steps`.
- `CandidateEvaluator.evaluate` passes that same `self.config.player` to `execute_player_run` for every candidate
  (`evolution/evaluator.py`, around line 66).

Changes:
1. **Option.** A new `research_moves_schedule` option (str, e.g. `"50,100,200,500"`, empty = flat `research_moves`).
   The last value repeats once the list runs out. Passed as `--player-max-environment-steps-schedule`.
2. **Evaluator.** Before `execute_player_run`, pick the rung by the number of completed evaluations:
   `dataclasses.replace(self.config.player, max_environment_steps=schedule[min(n, len - 1)])`. A crashed evaluation
   doesn't count, as today, so it retries on the same rung.
3. **Records.** Write the rung's budget into each evaluation record and into the candidate's `run_config.json`.
4. **Optimizer.** Its `status` / `inspect` and mission text say the next attempt's budget, so it can size its plan,
   e.g. "attempt 2 has 100 moves".
5. **Resume.** Keeps the schedule (`evolution_config.json`); `check_restart` refuses a changed schedule.
6. **Workbench.** The launch form picks up the option by itself. The campaign page needs one column: the budget per
   evaluation (`workbench/avo_console.py`, evaluations table).
7. **Related, already agreed in the Part 1 session:** a toggle so each hypothesis continues from the level where the
   previous one stopped. Fitness under `research` is then the farthest level reached; under `solver` the solver is
   still scored on the full game from level 1. It depends on Part 1's start-at-level-k.

### A2. Which score (Adam's choice)
- **Solver score:** each attempt must leave a `solver.py` that wins a fresh game alone (1000 moves).
  - The growing research budget doesn't bias the score: the solver is scored on a fixed budget.
  - But today no attempt produced a working solver in 2 hours. Knightoban's self-check sent ACTION5 500 times. A
    50-move first rung leaves even less to build a solver from.
- **Levels score (research):** the levels reached during the research session, built and never launched.
  - It measures what the 27B demonstrably does well: research and play.
  - But with a growing budget, later attempts get more moves, so "more levels" partly reflects the budget, not a
    better strategy.
  - To compare fairly, either look at levels per move, or compare only within a rung.

### A3. Expected time per attempt
Today's research pace, AVO v2 solver mode, 13:13 → 15:11:
- Modality: 93 moves in about 2 h, about 47 per hour.
- IceCrates: 101 moves, about 50 per hour.
- Knightoban: 415 moves, about 210 per hour.
- Most of the time went into thinking and writing the solver, not moves. The optimizer's first round took about
  4 minutes (13:09 → 13:13).

| Rung | Modality / IceCrates (about 50/h) | Knightoban (about 210/h) |
|---|---|---|
| 50 moves | about 1 h | about 15 min |
| 100 | about 2 h | about 30 min |
| 200 | about 4 h | about 1 h |
| 500 | about 10 h | about 2.5 h |

- A ladder of 50 → 100 → 200 → 500 is about 17 h for Modality/IceCrates and about 4 h for Knightoban, plus about
  5–10 min of optimizer per round.
- The levels score should be faster, since there's no solver to write; not measured yet.
- OpenRouter's speed per call depends on the host, unmeasured: our server gave about 84 tok/s per call.

### A4. Context overflow and AVO
- An AVO attempt is one long session, and all its thinking stays in the conversation: about 85k tokens of reasoning
  per session today.
- It's the most exposed framework:
  - AVO v1 Modality lost a whole attempt to an overflow at 203 moves;
  - AVO v2 IceCrates overflowed twice and recovered.
- On OpenRouter, without the `limit` declaration from section 0, it would never compact at all.
- Short early rungs (50, 100) keep the early attempts well under the limit. The 500 rung is where it bites.

## B. Harness² on Modality, per level, with a growing budget

### B1. State of the two sessions (read on 21 Oct evening; not messaged)
- **Part 1, "Per-level infrastructure (start at level k)":** plan agreed, **no code written**, no explicit "go" yet.
  - Decided with Adam:
    - options `start_level` (default 1) and `one_level` (default off), in the Baseline (both drivers) and AVO;
    - the player sees its level and the total (`level 3 of 4`);
    - the level mapping and bad-level errors live in `server.js`, which goes live only after a service restart;
    - the budget is just `max_steps`, set at launch; the shortest solution is metadata, recorded when known;
    - the AVO toggle "continue where the last hypothesis stopped" (section A1, item 7).
  - Last message: Adam asked what the difference between "default" and "solver" was, the session answered, and it is
    waiting.
  - `docs/research/per-level-interface.md` and `frameworks/level_task.py` don't exist yet.
- **Part 2, "Harness² per-level loop + escalating budget":** plan posted at 14:22, waiting on Adam's 4 answers:
  1. (a) every level starts from the empty harness and sees earlier levels only through the library (one extra
     "lesson" session per level), or (b) every level starts from the previous level's kept harness;
  2. the ladder multiples and the round cap;
  3. whether round n+1 starts from round n's kept harness or from the level's starting harness;
  4. whether the fresh "final" rollout runs per round, once per level, or not at all.

  No code written.

### B2. Minimal path to a real per-level Harness² run on Modality
- **Level 4 alone** is the target: shortest 158 moves.
  - Today's base1 needed 78 / 96 / 230 moves for levels 1–3, and failed level 4 in 596 moves.
  - Levels 1–3 are solved by every framework, so per-level runs on them add little.
  - Option: L3 and L4, so that L3's kept harness reaches L4 through the library or as its start (Adam's (a)/(b)).
- **Needs:**
  1. Part 1's start-at-level-k, including the `server.js` change and a service restart between batches.
  2. Part 2's level loop and ladder.
  3. Section 0's OpenRouter `limit` change.
- **Ladder for level 4** (158 shortest):

  | Round | Budget | Multiple of 158 |
  |---|---|---|
  | 1 | 316 | 2× |
  | 2 | 790 | 5× |
  | 3 | 1580 | 10× |

  Round cap 3; it stops at the first solved round. Each round: base rollout, then the INV and DOM coaches, then their
  two rollouts. agg and final are per Adam's question 4.

### B3. Why today's Modality coaching failed, and what would help
Measured from the three Modality coach sessions:
- **DOM** reached a 198k-token prompt, and one step hit the 64,000-token answer cap (`reason: length`).
- **INV's first session** reached 145k, hit the answer cap, then overflowed the context.
- **INV's retry** reached 193k.
- **The evidence pack:** base1's full trace is `context/inv1/rollouts/base1.md`, 264k characters, about 66k tokens.
  The mission adds about 14k characters.
- At max thinking, reading that trace plus thinking about it fills the context.

What would help, and how:
| Change | Kind | Expected effect |
|---|---|---|
| Coach effort `high` instead of `max` (`optimizer_effort`) | launch setting, new run only (resume refuses a change) | Less thinking per step: fewer answer-cap hits, slower context growth |
| Per-level rounds | comes with Part 2 | The pack holds one level's trace at the round's budget: 316 moves is about 85k characters, not 264k |
| Recursion `sequential` instead of `parallel` | launch setting | One stage at a time, each round composing a checkpoint from the earlier ones: fits rounds of a ladder; the two parallel sessions don't compete for the server |
| A bigger answer cap | code (`OUTPUT_TOKEN_MAX`, shared by all sessions) | Not possible above 65,536 on Chutes or Near AI. Not the fix |
| A shorter trace format (moves and diffs, not full boards) | code, upstream context builder | The biggest cut, but it changes what the coach sees: a methods change, to decide explicitly |

### B4. The wrong "hidden walls" model, and what a growing budget can and can't do
- Base1 explains every refusal as a per-edge wall. Both of today's Modality coaches wrote that model down as
  verified: DOM's `hidden-wall-sokoban` skill says "only a blocked move reveals a wall", and INV's planner keeps a
  per-edge wall map.
- In a per-level library this model would flow forward. Under (a) as a library entry, under (b) as the starting
  harness. A wrong prior would then be **inherited** by level 4 rather than discovered there.
- **A growing budget alone gives more of the same evidence.** Today, 596 moves on level 4 produced 108 bumps and no
  generalisation, and 1000 moves didn't find the rule.
- More rounds give the coach more chances to notice that every "wall" sits on a white–dark boundary. But nothing in
  the method pushes it to look for a cause behind the walls. Honest expectation: unlikely to find the rule by budget
  alone.
- A fair test pairs the ladder with H2: one true floor-colour note at the start. That separates "can't discover the
  rule" from "can't plan with it".

## C. Cost and time

### OpenRouter estimates
Priced on today's recorded tokens, at Near AI's prices; Chutes is a bit lower.
- **Today's references:**
  - Harness² base1 Modality, 1000 moves: $1.66.
  - Coach sessions on Modality: $0.48 for the three.
  - AVO v2: about $0.9–1.0 per game for its 2 hours.
- **AVO3, ladder 50 → 100 → 200 → 500:**
  - Research tokens scale with time, not moves: about $0.45 per hour per game.
  - About $7–8 for Modality or IceCrates (≈ 17 h) and about $2 for Knightoban (≈ 4 h).
  - **About $15–20 for all three games.** The levels score, with no solver, should cost less.
- **Harness² Modality level 4, 3 rounds** (316 / 790 / 1580):
  - Rollouts at about $0.0017 per move (today's base1):
    - round 1: 3 × 316 moves ≈ $1.6;
    - round 2: 3 × 790 ≈ $4.0;
    - round 3: 3 × 1580 ≈ $8.0.
  - Coaches about $0.5 per round.
  - **Worst case (unsolved after 3 rounds) about $15**; less if a round solves it.

### Wall-clock time
- Rollouts run in parallel; 1000 moves took 2 h 27 today.
  - Round 1 ≈ 45 min of rollouts + 40–60 min of coaching.
  - Round 2 ≈ 2 h + coaching.
  - Round 3 ≈ 4 h + coaching.
- Worst case about 9–10 h for Harness² Modality level 4.
- AVO3 is bounded by its slowest game (≈ 17 h on the full ladder).

### Against the vast instance
- At $5.763/h, the same 10–17 h would cost $58–98 in GPU time, against about $30–35 on OpenRouter for both runs
  together.
- OpenRouter also has no upper limit of 16 parallel calls; the hosts' rate limits are the unknown.
