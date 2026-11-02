# Experiment spec: frameworks on a self-hosted 8-bit Qwen 3.8 27B (draft, 21 Oct 2026)

Nothing is launched until every **Decision** below is settled.

## Fixed for every run

| setting | value |
|---|---|
| model | Qwen 3.8 27B, Qwen's official 8-bit weights (`Qwen/Qwen3.8-27B-FP8`) |
| thinking | maximum everywhere (player, coach, optimizer); what "max" maps to on this server is being checked by the setup session |
| server | vLLM on the rented 4× RTX 5090 (vast.ai), model split over the 4 cards, every run batched on the one server; conversation memory (KV cache) also in 8-bit so all runs fit at once; no 16-bit anywhere |
| sampling | **Decision 6** |
| agent CLI | OpenCode, one Docker container per run |
| games | Modality (4 levels), IceCrates (6), Knightoban (6) |
| input | grid and picture, every turn |

## Frameworks and budgets

| framework | player | game actions | stages |
|---|---|---|---|
| Baseline | turn-based: one action per reply, one conversation, a `notes/` folder | 1,000 | 1 game |
| AVO | its own agentic research agent, then a solver | 10 iterations × 500 research actions | iterations run one after another |
| Harness² | the agentic player (plays through `python game.py`) | 5 games × 1,000 (base, INV, DOM, merged, final) | 4 stages run one after another |

Harness² budget (decided 21 Oct): it gives each Harness² game the same 1,000 actions as Baseline, and the same 5,000 in total as AVO.

## What every run must leave behind

1. **The full reasoning of every session** (player, coach, optimizer), with timestamps. OpenCode sessions already save it in `agent_events.jsonl`. Still to check for AVO's sessions.
2. **`world.md`**, one rules file kept by the player, in the same format in every framework:
   - sections: controls; movement; objects and what they do; pushing; what completes a level; open questions;
   - each rule is marked *confirmed* or *guess*.

   Copies are saved after every 100 actions, after every completed level, and at the end (**Decision 4**). Where it comes from in each framework:
   - **Baseline:** `notes/world.md`, which it is told to keep.
   - **AVO:** the research agent's world model at the end of each iteration, plus the same copies during research.
   - **Harness²:** each of its 5 games keeps `world.md`. The coach's harness files are saved per stage (already done).
3. **Grading.** Every copy, and the reasoning, is graded against the game's true rule list. This gives:
   - a curve of rules correct against actions;
   - the action at which each rule was first stated correctly;
   - the wrong rules still held at the end.

## True rule lists

- **Modality** (checked against the game's source; shortest solutions 6/33/66/158):
  1. ACTION1–4 = up/down/left/right.
  2. ACTION7 = undo.
  3. You cannot step directly between white and dark.
  4. Grey connects white and dark.
  5. Walking into the box pushes it one cell.
  6. A push needs matching floors: white/grey with white/grey, dark with dark.
  7. A level is won when the box is on the blue target.
- **IceCrates** (6 levels; verified on the engine and by playing all 6 levels with a solver built from this list; `studies/thursday/rules/icecrates.md`):
  1. ACTION1–4 = up/down/left/right; there is no ACTION5.
  2. ACTION7 undoes one action (a whole slide).
  3. The player slides until the next cell is blocked.
  4. Walls and water stop the player.
  5. Sliding into a crate pushes it: crate and player slide together until the crate is blocked. A crate that can't move works like a wall.
  6. Touching crates move as one line. If the front crate is blocked, the line stays.
  7. A crate pushed into water fills it; filled water is floor.
  8. A level is won when the player stops on the goal (sliding across it doesn't count).
- **Knightoban** (6 levels; verified the same way; `studies/thursday/rules/knightoban.md`):
  1. ACTION1–4 move one cell; ACTION5 only acts while a crate is lifted.
  2. ACTION7 undoes one action, including each change of choice.
  3. Walls block.
  4. Walking into a crate puts the player in its cell, and the crate jumps like a chess knight (2 ahead, 1 to the side), over anything.
  5. While a crate is lifted the player cannot move. The arrows switch between the two landing squares, and ACTION5 places the crate.
  6. Squares holding a wall or crate are not offered; if none is free, nothing happens.
  7. A level is won when every target has a crate.

  The script also defines a plain crate, but no level contains one. A player who claims plain Sokoban pushing is wrong.

## Measures

- **Performance:** rules correct at the end, and over time (from the `world.md` copies and the reasoning).
- **Cost:** GPU hours used by the run (the machine's $5.76/hour divided by the runs sharing it), and tokens written.
- **Secondary:** levels completed, and actions per level.

## Robustness: we get one try

- Tool calls are checked on the server before launch: 16 of 16 must come back as real tool calls.
- A failed turn is answered with a new turn. Three failures in a row start a fresh session in the same folder. Both are logged.
- Context (decided 21 Oct): a 1,000-action game passes the 262k-token limit (games reached 210k–261k by 200 actions). OpenCode compacts: it replaces old turns with a summary the model writes. This needs the model's context limit declared in the provider config. The player's notes and `world.md` survive compaction. A fresh session that keeps the files remains the fallback.
- Before the batch, a 3-action smoke of each framework on the server.

## Time and cost (estimate)

- 8-bit weights take about 28 GB, which leaves about 90 GB for context: room for about 10–15 games at once.
- At about 3 actions a minute per game:
  - Baseline: 6–10 h;
  - Harness²: about 20–25 h (stages in a row);
  - AVO: about 25–30 h (iterations in a row).
- Batching does not shorten AVO or Harness², because their stages run in sequence.
- The full set is about 1–1.5 days on the machine (about $140–200). Shrinking the budgets shrinks the time in proportion (**Decision 1**).

## Baseline prompt (draft, Decision 5)

System:

> You are playing an unknown puzzle game. Each turn you get the current frame, as a picture and a grid, and reply with exactly one action. Your working directory has frame.png and a notes/ folder. Keep notes/world.md up to date: the rules you have confirmed, the rules you only suspect, and what completes a level. Update it whenever a move confirms or breaks a rule, or a level changes. You may create other files. Finish file work before your one-action reply.

Each turn (as now):
- what the last action changed, with "LEVEL COMPLETED (k/n)" when a level ends;
- the state, levels, available actions and actions used out of the budget;
- the grid;
- "Choose the single next action."

## Decisions

1. Budgets as above (about 1–1.5 days), or smaller to fit fewer hours?
2. ~~Harness² budget~~: decided, 5 games × 1,000.
3. ~~Context~~: decided, OpenCode compaction, with a fresh session as fallback.
4. `world.md` copies: every 100 actions, every level, and the end?
5. Baseline prompt: as drafted?
6. Sampling: Qwen's recommended thinking settings, or the server's defaults? Either way, record them.
