# Why Qwen 3.8-27B stalls on Modality level 2

Analysis date: 2026-10-08. Sources: existing run logs (no new model calls).

## Ground truth (`puzzlescript_interface/games/ps_modality-v1/script.txt`)

- The player cannot step directly between white and black floor. Grey (the
  checkered tile) bridges them.
- A crate is pushed only when the player and the crate stand on compatible
  terrain: both non-black, or both black.
- ACTION7 is undo. Win: every crate on a target.
- Level 2: the player starts on white at (0,4). The crate sits on black at
  (1,2), and the target is white at (2,0).
- Solution: go along white to the grey tile (3,1), then into black. Push the
  crate left twice, which moves it onto white at (1,0). Return to white via the
  grey tile and push the crate down onto the target.

## What 27B believed

Runs: `output/workbench/20260930T224156-3572b5fe` (max effort, 95 decisions,
124 transitions) and `20261001T000258-18c731e5` (high effort, 36 decisions).
Both cleared level 1, and neither cleared level 2. Both were stopped by hand
for budget.

| Mechanic | 27B's model (both runs) | Correct? |
| --- | --- | --- |
| Arrow keys | up/down/left/right, found in ~4 moves | yes |
| ACTION7 | "fires a shot" (run B); "jumps 1 tile opposite the facing direction, and a checkered tile is a trampoline" (run A) | **no**: it is undo. Undoing a move looks like jumping back, and the model never tested the simpler explanation |
| Colour blocking | "white tiles are walls" (L1); "in level 2 dark tiles may be walls" (L2) | **partly**: it sees the blocking but makes it a per-level wall map, not "no direct colour crossing" |
| Grey/checker | trampoline / elevator / a "crossing" (run B) | partly |
| Orange crate | "goal frame you enter from below" (B); "decoy, unreachable object" (A) | **no**: never treated as pushable |
| Level-1 win | accidental: "testing if the orange frame is enterable from below" pushed the crate onto the target | the win reinforced the wrong goal theory |
| Level-2 plan | enter the orange "goal" from below (B); exhaustively test jump-landings onto "sealed" tiles (A) | no |

Run A's own note ("L1 pattern: unreachable object = decoy, reachable object =
goal") shows the model generalising a superstition from one accidental win.

## What GPT-5.5 believed on the same game

Run: `output/codex_agent/modality-55-high-baseline-plus-1000-20260907T181409-r3`.
Same baseline-plus harness, same note tools. 3/4 levels.

- Strategy version 10 (about 4 minutes in): "ACTION7 is likely reset/undo", tested
  and confirmed by version 12 as "undo one move".
- Right after level 1: "Orange blocks are Sokoban-like pushable blocks. Level 1
  was solved by pushing orange from (1,0) upward onto purple."
- By version 20: "light player cannot enter dark tiles directly; checker tile
  4 switches between light and dark". Level 2 solved.

## Failure category

This is **not** a protocol or perception failure. 27B uses the note tools,
returns valid actions, and tracks coordinates and tile IDs correctly. The
failure is in **hypothesis formation and revision**:

1. It does not reach for common priors: no "undo" for an unexplained
   reversing action, and no "Sokoban push" for a box-and-target layout. Instead
   it builds elaborate novel theories (jump-opposite-facing, trampolines,
   decoys).
2. It explains away evidence locally instead of looking for the simplest
   global rule (walls redefined per level).
3. It credits an accidental success to the wrong cause and keeps that
   explanation.

Implications for the three hypotheses:

- *Pretraining:* GPT-5.5 names the genre ("Sokoban-like") and the undo key
  immediately. 27B never does. This is consistent with missing exposure to
  grid-puzzle conventions. It is still one game and two runs, so not proof.
- *Harness:* candidate interventions target revision, not protocol:
  - require listing ≥2 competing explanations for each surprising transition,
    including "undo/reset";
  - a "what caused the level win?" replay step after each level;
  - a hint "this may be a known puzzle genre; name it".

  Each is testable as a single ablation.
- *Size:* run Qwen 3.8 Max on the same level and check whether it reaches
  "undo" and "push" from the same evidence.

## Precision control (2026-10-08)

The Modality rerun pinned to Alibaba (the first-party provider, so not a
quantized third party) used the same baseline+ harness at high effort:
`output/workbench/20261008T112945-f705fa9a`.

It scored **0/4 levels in 100 actions**, worse than the unpinned runs, which
cleared level 1 by accident. The beliefs only partly changed:
- This time it called the crate a "pushable Sokoban box".
- By decision 7 it still called ACTION7 a "jump" (30 mentions, never
  "undo"), and it called the checkered bridge a "pit".
- It pushed the crate into a corner, which it judged "permanently stuck", so
  it failed at planning without undo.

Provider quantization does not explain the failure.

Same day, same settings:
- Knightoban: 0/6 in 120 actions.
- IceCrates: 3/6 after 99 actions. This is the first game where 27B makes
  real progress, and its mechanic (sliding plus pushing a crate train) is
  closer to common ice-puzzle conventions.
