# Task

You are playing an unknown game. Your goal is to win.

Infer the mechanics and the concrete win condition from observations and interaction.
Available action IDs are opaque. Environment actions are costly, so use internal reasoning,
notes, code, replay, and executable hypotheses freely between actions.

Do not stop merely because a hypothesis is accurate. The task succeeds only when the
environment evaluator reports success.

Frame values are anonymous, stable IDs for visually distinct rendered cells. They do not
name objects or expose hidden state. Use the last grid in `frame` as the current board;
earlier grids are intermediate animation states from the same action.
`metadata.projection.patterns` gives the anonymous 5x5 visible color pattern represented
by each cell ID, preserving the same shapes, overlays, and color relationships a player sees.

Once transitions appear deterministic, prefer a systematic reversible state search over
random action sequences. If an action restores the preceding observation, it can be used
to explore branches without repeatedly discarding progress. Do not call `finish` while
the evaluator still reports failure and a materially different test remains possible.
Use environment checkpoints to preserve hard-won positions before testing alternative
continuations; restore the checkpoint instead of replaying or resetting the entire level.
