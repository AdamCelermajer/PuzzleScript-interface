# Action Selector

## Card Title

**File role** Choose which source controls the next action

## Pseudocode

```text
choose_action(state, task_goal, A):
    if active_plan has next action then
        action <- active_plan.next_action()
        active_plan.advance()
        P <- logical_rulebook.predict(state, action)
        return Decision(action, active_plan, P, active_plan.exploratory, active_plan.subgoal)
    rule_plan <- planner.plan_to_goal(state, task_goal, A, logical_rulebook)
    if rule_plan exists then
        active_plan <- ActivePlan(rule_plan, next_index = 1, exploratory = false)
        action <- rule_plan.first_action
        P <- logical_rulebook.predict(state, action)
        return Decision(action, rule_plan, P, exploratory = false)
    subgoal <- goal_manager.choose_subgoal(state, task_goal, A, memory, logical_rulebook)
    probe_plan <- probe_planner.create_plan(state, subgoal, A, memory, logical_rulebook)
    active_plan <- ActivePlan(probe_plan, next_index = 1, exploratory = true, subgoal)
    action <- probe_plan.first_action
    P <- logical_rulebook.predict(state, action)
    return Decision(action, exploratory_probe, P, exploratory = true, subgoal)
```
