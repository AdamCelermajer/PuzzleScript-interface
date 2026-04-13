# Next Week - Professor Homework

## Todo

- [ ] Task 1: add the possibility to replace the normal ASCII legend/view with the in-game representation when needed.
- [ ] Confirm the exact scope of the switch: terminal dashboard only, runtime output, or both.
- [ ] Trace the current legend/render path in `puzzlescript_interface/runtime/server.js`.
- [ ] Trace the ARC projection mapping in `puzzlescript_interface/runtime/arc_projection.js`.
- [ ] Trace the board rendering in `client/terminal_dashboard.py`.
- [ ] Implement a switch or toggle between the current ASCII view and the in-game representation.
- [ ] Validate the result on `puzzlescript_interface/games/ps_sokoban_basic-v1/script.txt`.
- [ ] Validate the result on at least one more game, such as `puzzlescript_interface/games/ps_midas-v1/script.txt`.

- [ ] Task 2: fix `docs/architecture/arc-agi-architecture.svg`.
- [ ] Review the SVG against the current repo structure.
- [ ] Fix any outdated or misleading architecture details.
- [ ] For each major module, add high-level Python-style pseudocode.
- [ ] Cover at least these modules: environment, LLM reasoning core, context window, transition buffer, rule induction pipeline, subgoal engineering, and persistent knowledge store.
- [ ] Check that the diagram and pseudocode match the code in `client/` and `puzzlescript_interface/`.

- [ ] Task 3: read Shen (1993), "Discovery as autonomous learning from the environment".
- [ ] Write down what ideas are worth taking into this project.
- [ ] Write down what should not be taken, or cannot be applied here.
- [ ] Analyze where the paper's algorithm would likely succeed in these games.
- [ ] Analyze where the paper's algorithm would likely fail in these games.
- [ ] Prepare short talking points for the next meeting.

## Time Estimate

- Task 1: 3 to 6 hours
- Task 2: 2 to 4 hours
- Task 3: 4 to 6 hours
- Total: 9 to 16 hours

## Notes

- Task 1 is the most ambiguous and probably needs a quick scope check before implementation.
- The architecture SVG already exists at `docs/architecture/arc-agi-architecture.svg`.
- The paper task is feasible, but it needs real reading and synthesis time.

## Likely Paper Angle

- Likely succeeds best in simple, deterministic, local-rule games such as basic Sokoban.
- Likely struggles more in games with hidden state, mode switches, long-range dependencies, or sparse feedback.

## Help I Can Provide

- I can help implement the optional representation switch.
- I can help fix the architecture SVG and write the pseudocode.
- I can help read the paper and turn it into meeting notes.
