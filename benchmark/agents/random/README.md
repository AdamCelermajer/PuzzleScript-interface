# Random agent

The minimal action baseline. It selects uniformly from advertised
`ACTION1`–`ACTION5` actions and never uses evaluator artifacts. The dashboard
launches the fixed scenario in `scenario.json` as a background run with a
0.5-second delay between actions.

It is kept separate from the partial-success fixture because a random policy
does not produce meaningful rule predictions.
