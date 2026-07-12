# Planner

## Card Title

**File role** Choose the next action

## Pseudocode

```text
s <- memory.current_state()
A <- available_actions(s) # exclude RESET
if active plan has next action then
    active_plan.advance()
    return PlanDecision(next action, active_plan, exploratory = active_plan.exploratory)
if game_goal = null then
    game_goal <- goal_manager.ensure_goal(memory)
plan <- plan_to_win(s, A) # BFS over rule predictions
if plan != null then
    active_plan <- ActivePlan(plan, index = 1, exploratory = false)
    return PlanDecision(plan[0], rule_plan)
goal <- goal_manager.ask_for_subgoal(llm, s, A, rulebook.known_rules_text())
probe <- goal_manager.ask_for_action_plan(llm, s, A, goal, rulebook.known_rules_text()) # short list, 1-5 actions
active_plan <- ActivePlan(probe, index = 1, exploratory = true)
return PlanDecision(probe[0], explore_subgoal, plan = probe, exploratory = true)
```
