# Rule Planner

## Card Title

**File role** Search for a plan using verified rules

## Pseudocode

```text
plan_to_goal(state, task_goal, A, logical_rulebook):
    queue <- [(state, empty_plan)]
    seen <- {state}
    while queue is not empty do
        (predicted_state, plan) <- queue.pop_front()
        if task_goal.reached_by(predicted_state) then return plan
        if plan reached search depth then continue
        for all action in A do
            next_states <- logical_rulebook.predict(predicted_state, action)
            for all next_state in next_states do
                if next_state not in seen then
                    seen.add(next_state)
                    queue.push(next_state, plan + action)
    return no_plan
```
