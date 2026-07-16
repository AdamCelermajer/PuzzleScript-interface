# Main Runtime Loop

## Card Title

**Main loop** Runtime <-> engine modules <-> ARC/PuzzleScript engine

## Pseudocode

```text
frame <- env.reset() # ARC/PuzzleScript starts the game
(state, legend) <- perceiver.initial_perception(frame)
memory.append_state(state)
game_id <- cfg.game or state.game_id
task_goal <- goal_manager.infer_task_goal(state, legend) # stable objective for this run
while steps < max_steps and not task_goal.reached_by(state) do
    A <- available_actions(frame, state) # exclude RESET
    decision <- action_selector.choose_action(state, task_goal, legend, A)
    outcome <- action_executor.execute(frame, state, decision) # env.step + perceive
    memory.append_action_result(outcome, prediction_context = decision)
    contradicted_G_rules <- logical_rulebook.record_prediction_result(state, outcome.action, outcome.after_state, decision.predictions)
    contradicted <- decision.predictions exist and outcome.after_state not in decision.predictions
    unexplained <- decision.predictions are empty
    if contradicted or (unexplained and not decision.exploratory) then
        action_selector.invalidate_active_plan() # unknown exploratory effects can continue
    if contradicted then
        learning_result <- rule_learner.revise(contradicted_G_rules, outcome, memory) # links matching NL rules
    else if unexplained then
        learning_result <- rule_learner.learn_from_memory(game_id, legend, memory)
        if learning_result is stop_required then
            return stopped_after_repeated_rule_learning_failures
    frame <- outcome.after_frame
    state <- outcome.after_state
    if frame.state is GAME_OVER then
        frame <- env.reset()
        state <- perceiver.perceive_state(frame)
        memory.append_state(state)
return success if task_goal.reached_by(state) else step_budget_exhausted
```
