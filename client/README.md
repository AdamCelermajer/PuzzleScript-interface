# Client

`client/` contains the ARC-compatible command-line entry points and the shared agent runtime.

## Main Scripts

- `run_arc_agent.py` runs the learning or solving agent against an ARC-compatible backend, including the local PuzzleScript service and the official ARC-AGI-3 endpoint.
- `play_arc_client.py` lets a human play a local ARC-compatible PuzzleScript game from the terminal with keyboard controls.
- `terminal_dashboard.py` renders the live terminal UI used by both the automated agent runner and the manual play client.
- `python -m client.live_sokoban.run` runs the single LIVE-style Sokoban POC against the local PuzzleScript ARC service.

## Rules Output

During learning runs, the agent writes readable evidence and rule artifacts under `client/rules/<game-id>/`: `transitions.jsonl`, `rules.json`, `rules.md`, and `journal.md`.

Action choice is engine-first, then LLM-guided: the planner uses verified executable rules when they can reach a goal, and otherwise asks the LLM for a small subgoal and short legal action plan. The engine still records the real transition afterward, so the LLM proposal becomes evidence instead of trusted truth.

## LIVE Sokoban POC

`client/live_sokoban/` is the only supported LIVE-style PuzzleScript experiment. It represents state as neutral percepts: generalized wall facts, singleton `P`, numbered targets such as `O1`/`O2`, numbered crates such as `*1`/`*2`, derived covered-target facts such as `@1`, changed cells, and an observed `O/@` base layer. It does not encode Sokoban object names, push mechanics, or action directions.

The rule model attributes raw controller actions to the observed actor, for example `ACTION2(P)`, then learns readable `At(...)` / `NOT At(...)` conditions and add/remove effects. A push rule is shown as `At(P,x,y) AND At(*a,x,y+1) AND NOT At(#,x,y+2) AND NOT At(*b,x,y+2)`, followed by predictions such as `NOT At(P,x,y)` and `At(*a,x,y+2)`. Symbol-line forms like `P * . -> . P *` are only the visual observation, not the stored rule. When a prediction fails, it keeps the failed parent visible and creates complementary sibling rules so the next prediction can prefer the most specific matching context. Outputs are written to `client/live_sokoban/output/live_rules.md`, `live_rules.json`, and `live_journal.md`.
