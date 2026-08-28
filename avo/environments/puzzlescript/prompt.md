# Task

You are playing an unknown game. Your task is to build a reusable autonomous solver,
not to solve the game directly. Environment interaction is research used to learn and
validate the solver. Progress achieved through actions chosen manually by you is not the
final answer.

Infer the mechanics and the concrete win condition from observations and interaction.
Maintain an executable `solver.py` that observes the current state, retains any necessary
hidden-state history, plans actions using its learned environment model, and can solve from
a fresh reset without further Codex reasoning. Before finishing, validate the solver from
reset. The solver is the deliverable.

`python solver.py` must implement the documented theory-prediction JSON protocol. For an
unseen state and proposed action, predict the next observation from learned rules rather
than replaying that action in the real environment or merely recalling an identical prior
transition. `python solver.py --play --max-steps N` must autonomously play from the current
observation. Plan by rolling the learned model forward internally; real probes and
checkpoints are research and validation tools, not the solver's planning mechanism.

After research, the trusted evaluator launches `solver.py` alone in a second fresh game.
Fitness is the number of levels it completes multiplied by prospective model accuracy on
the fresh transitions. Progress made manually during research earns no fitness.
Available action IDs are opaque. Environment actions are costly, so use internal reasoning,
notes, code, replay, and executable hypotheses freely between actions.

Do not stop merely because a hypothesis is accurate. The task succeeds only when the
environment evaluator reports success.

Frame values are anonymous, stable IDs for visually distinct rendered cells. They do not
name objects or expose hidden state. Use the last grid in `frame` as the current board;
earlier grids are intermediate animation states from the same action.
`metadata.projection.patterns` gives the anonymous 5x5 visible color pattern represented
by each cell ID, preserving the same shapes, overlays, and color relationships a player sees.

The environment may be partially observable: identical visible observations can correspond
to different latent states and produce different transitions. When evidence conflicts,
consider recent action and observation history, model possible hidden modes, and test them
deliberately rather than forcing a purely visible-state model.

Once transitions appear deterministic, prefer a systematic reversible state search over
random action sequences. If an action restores the preceding observation, it can be used
to explore branches without repeatedly discarding progress. Do not call `finish` while
the evaluator still reports failure and a materially different test remains possible.
Use environment checkpoints to preserve hard-won positions before testing alternative
continuations; restore the checkpoint instead of replaying or resetting the entire level.
