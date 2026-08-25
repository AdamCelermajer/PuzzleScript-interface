# Nine previous BFS timeouts: exact-solver result

Scope: the first playable map of the nine games that timed out in
`semantic_all_60s_results.json`. This is the same case selection used by that
older BFS run; it is not a claim that every map in each multi-level game has
been solved.

| Game | Inputs | Search graph | Replay |
|---|---:|---|---|
| `ps_fire_in_winter-v1` | 65 | compiled portal/burn rules | pass |
| `ps_self_alteration-v1` | 22 | compiled alteration/trail rules | pass |
| `ps_collapsing_tiles-v1` | 14 | complete engine state | pass |
| `ps_fuse_to_green-v1` | 19 | compiled slide/fusion rules | pass |
| `ps_dark_pellets-v1` | 21 | compiled pellet/trail rules | pass |
| `ps_infected-v1` | 27 | compiled chain/infection rules | pass |
| `ps_extra_push-v1` | 42 | complete engine state | pass |
| `ps_the_art_of_storage-v1` | 51 | compiled push/spawn rules | pass |
| `ps_side_painting-v1` | 34 | compiled paint/pull rules | pass |

Total: 9/9 solved, 295 external directional inputs.

## What “exact” means here

Every edge costs one external input. A* accepts a goal only when it is removed
from the minimum-`f` queue, and every heuristic is a lower bound.

Two games search the serialized PuzzleScript machine state directly. Seven use
a source-signature-gated compiler that removes animation, facing, derived
markers, and rule machinery after preserving the rule-relevant state. Each
compiled profile lists its equivalence assumptions as certificates in the
result. These certificates are reviewable source checks, not a machine-checked
formal proof of the PuzzleScript implementation.

Every returned action sequence is independently replayed through
`PuzzleScriptMachineAdapter`; a result is saved only if the real engine wins on
the final action and not earlier.

The full action sequences and search counts are in `solutions.json`.
