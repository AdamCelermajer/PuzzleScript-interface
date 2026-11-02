# Task

Build `solver.py` for this unknown game. Interaction is research; manually completed
levels do not count as fitness.

The solver is a persistent streaming controller:

```text
python solver.py --play --max-steps N
```

For each JSON observation on stdin, emit exactly one JSON line:

```json
{"action":"ACTION_ID"}
```

Each stdin line is `{"observation": {...}}`. Its `payload.frame` holds one grid, the current
board: the same rows `probe` and `observe` print. `status`, `progress` (`levels_completed`,
`win_levels`) and `available_actions` match what they print; `metadata.projection.mode`
names the grid encoding.

The evaluator runs the solver alone from a fresh reset. Fitness is the number of levels
it completes there.

During implementation, `evaluate_solver` provides at most two provisional fresh-game
self-checks. They do not own fitness; use them to catch and repair solver regressions
before the independent final evaluation.

Action IDs and board values are opaque; infer their meaning from observed transitions.
The game may contain hidden state, so the solver may retain action and observation history.
Plan internally rather than using real checkpoints as the solver's search mechanism.

The board's encoding is named next to it. The default, `visible-cell-v1`: each grid cell
is one visible game tile. Identical rendered textures share an anonymous integer ID;
hidden object differences are not encoded. Visibly different textures have different
IDs. IDs remain stable within a session and can exceed 15. This is an observation
encoding, not a rule or object-name legend.

For explicitly configured legacy `visible-cell-hex-v2`, each visible tile is encoded
as a 2x2 block `[[a,b],[c,d]]`. Decode its opaque pattern ID as
`4096*a + 256*b + 16*c + d` before treating it as one board tile. This is an
observation encoding, not a rule or object-name legend.

When the encoding is `object-cell-v1`, each grid cell is one visible
game tile. Values are anonymous object-combination IDs, not texture or color IDs.
Overlapping gameplay objects remain distinct combinations.

Run `python avo_tool.py image` to request the current visible state's lossless PNG, then
open the returned `rendered_frame.path` with your own file or image tool when shapes, colors, or overlays
matter. This does not take a game action. `probe` and `observe` also print the current
board's image path, and `history --move N` that of a past move's final board, for visual
comparisons.
