# Fixed partial-success agent

This deterministic fixture makes the browser dashboard show a stable,
non-perfect benchmark result.

It always uses the three games and solution fractions in `scenario.json`:

- Sokoban Basic: completes the selected level;
- Coin Counter: stops around 56% through the verified path;
- Wall Shuffle: stops around 55% through the verified path.

Rule predictions begin at 4/10 correct and improve at later Sokoban
checkpoints, ending at 8/10 after level completion.

The dashboard starts this fixture in the background and refreshes while it
plays, with a 0.5-second delay between actions.

The fixture deliberately reads evaluator artifacts to manufacture exact,
repeatable scores. It is for UI tests and demonstrations, not a valid agent
submission.
