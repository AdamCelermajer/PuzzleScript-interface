# Main Runtime Loop

## Card Title

**Main loop** Runtime <-> engine modules <-> ARC/PuzzleScript engine

## Pseudocode

```text
frame <- env.reset() # ARC/PuzzleScript starts the game
state <- perceiver.perceive(frame)
memory.append_state(state)
game_id <- cfg.game or state.game_id
while steps < max_steps do
    decision <- planner.choose_action(state)
    P <- rulebook.predict(state, decision.action)
    outcome <- action_executor.execute(frame, state, decision) # env.step + perceive
    rulebook.record_prediction_result(state, outcome.action, outcome.after_state, P)
    memory.append_action_result(outcome.action, outcome.after_state)
    contradicted <- (P is not empty) and (outcome.after_state not in P)
    unexplained <- (P is empty) or contradicted
    if contradicted or (P is empty and not decision.exploratory) then
        planner.clear_llm_plan() # unknown exploratory effects can continue
    if decision.exploratory or unexplained then
        inducer.propose_from_memory(game_id, memory)
    if state.is_win() then return success
    if game over then reset env and continue
    state <- outcome.after_state
```
