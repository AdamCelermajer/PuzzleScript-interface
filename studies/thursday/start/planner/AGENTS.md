# A planning tool

scripts/search.py finds the shortest list of actions that reaches a goal, using rules you write as Python code. It costs no game actions, and it is only as right as your rules.

Write a file, for example rules.py, with three functions:
- start(): the current state, any hashable value (for example a tuple of positions);
- moves(state): a list of (action, next_state) pairs, one for each action that changes the state;
- done(state): True when the level is complete.

Then run: python scripts/search.py rules.py
It prints the actions in order, or "no solution".
