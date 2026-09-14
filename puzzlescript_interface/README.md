# PuzzleScript Interface

`puzzlescript_interface/` contains the local PuzzleScript workflow used by the root README:

- `runtime/` contains the Node.js PuzzleScript runtime.
- `api/` contains the ARC-compatible Python service.
- `games/` contains PuzzleScript game folders in the `name/script.txt` layout.

## Run Locally

From the repository root, start the PuzzleScript runtime:

```bash
npm start
```

Start the local ARC-compatible PuzzleScript service:

```bash
uv run python -m puzzlescript_interface.api.main
```

Then run the client from the repository root:

```bash
uv run python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --max_steps 50
```

This agent command requires `OPENROUTER_API_KEY`.

The runtime writes session history under the ignored `puzzlescript_interface/.runtime/` directory.

## Observation contract

Every game, including arbitrary submitted source, defaults to `visible-cell-v1`: one integer cell per
visible tile. IDs are assigned to the final rendered RGBA pixels, using the same
compositor and camera as the PNG. Identical textures share an ID even when hidden
engine objects differ. Visibly different textures remain distinct, including
wall variants and visible overlays; no object names or semantic wall categories
are used. IDs are stable within the session, including RESET/Undo, and range from
0 to 65,535, allocated only as textures appear. `projection.patterns` contains only textures already observed.
`max_combinations: 65536` declares this extended, nonstandard ARC range. Overflow
fails explicitly instead of merging visibly different tiles.

This replaces the title-dependent defaults, including `object-cell-v1`, which exposed
invisible state distinctions. Start fresh experiments with the new encoding;
do not replay old object-grid observations as if they were texture observations.
Existing sessions/services are not automatically restarted. Historical results
remain evidence for the older object representation, not the new one.

Validation: 145 selected maps, 52 recorded solutions, and additional probes;
largest observed session dictionary: 38 textures. This is not exhaustive coverage.
Reproduce with `node output/game-selection-20/verify-visible-128.cjs`.
The rendered Enqueue comparison and audit are in
`output/game-selection-20/visible-texture-grid/`.

There are no game-title exceptions. To explicitly select the legacy visual hex
encoding, set `PUZZLESCRIPT_GRID_ENCODING=visible-cell-hex-v2` before starting Node.
The default is `PUZZLESCRIPT_GRID_ENCODING=visible-cell-v1`; unknown modes fail at startup.
Both encodings
use visible pixels; the numbered grid still provides tile segmentation and exact
texture matching, so it is not equivalent to an image-only observation.

The `visible-cell-hex-v2` projection represents each visible tile with a 2×2 block
`[[a, b], [c, d]]` of integers from 0 to 15. Its opaque pattern ID is
`4096*a + 256*b + 16*c + d`. Grid dimensions are twice the visible board dimensions.
`projection.patterns` maps these IDs to full RGBA sprite pixels; IDs carry no object
names or game rules. This preserves up to 65,536 distinct rendered tile patterns
per session without merging them into the same value. Exceeding that limit fails
explicitly. The PNG and encoded grid use the same native flickscreen/zoomscreen
viewport. `projection.board_shape` gives the visible tile rows and columns.

Message levels are skipped without consuming a gameplay action. This includes
introductory and between-level text; agents must infer mechanics from gameplay.
Completing the final playable map reports `WIN` and all playable levels completed,
including when the source ends with a message screen.

For the full installed catalog audit, run `node scripts/audit_visible_textures.cjs`.
Results are written to `output/global-visible-texture-audit/`. It checks each map
and bounded action probes, not every reachable state. Malformed source levels and
worker timeouts are reported as failures, never silently counted as supported.
The 2026-09-09 audit passed 188 of 193 installed games, checking 1,596 maps and
10,313 frames; Snakehole reached 668 textures. See `report.md` in that output
directory for the five remaining engine/source/timeout failures. These counts
are an audit snapshot, not a guarantee for future game sources or unvisited states.
Existing running Node processes must be restarted separately to load changes.
