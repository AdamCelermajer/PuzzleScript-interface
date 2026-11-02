# Task

Advance as far as possible through this unknown game. There is no solver: the levels you
complete during this research session are the score, and fewer actions breaks ties.
Every session starts from a fresh reset, so earlier levels must be passed again.

Action IDs and board values are opaque; infer their meaning from observed transitions.
The game may contain hidden state.

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
