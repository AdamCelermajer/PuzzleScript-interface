# IceCrates (`ps_icecrates-v1`): true rules

The rule list for grading the players' `world.md`. Checked against
`puzzlescript_interface/games/ps_icecrates-v1/script.txt` and played on the local engine
(`http://127.0.0.1:8000`), 21 Oct 2026.

- **6 levels.** Actions offered: ACTION1–4 and ACTION7 (`available_actions: [1, 2, 3, 4, 7]`).
- Notation: U D L R = ACTION1–4, Z = ACTION7. Cells are (row, column) in the level map as written in
  the script, (0, 0) top left. Level 1 was played from a plain `RESET`; later levels were opened with
  `RESET` + `level_index` (level k = index 2k−1), and all six were also played through in one session
  (end of file).

## Rules

1. ACTION1–4 move up, down, left, right; there is no ACTION5.
2. ACTION7 undoes the last action, a whole slide at once (with any crate pushed or water filled); RESET restarts the level.
3. The player slides in the pressed direction until the next cell is blocked; it cannot stop on open floor.
4. Walls and water stop the player on the cell before them; the player never enters water.
5. Sliding into a crate pushes it: crate and player slide on together until the crate is blocked, and the player stops right behind it; a crate that cannot move stops the player like a wall.
6. Crates in a line move together, including resting crates that a pushed crate runs into; if the front crate is blocked, the line stays and the player stops behind it.
7. A crate pushed into water sinks: the crate disappears, the water cell becomes a brown filled floor that the player and crates slide over, and the slide goes on.
8. The level is won when the player stops on the goal; sliding across the goal does not count.
9. Water tiles animate: their look changes on every engine tick (a cycle of 5 textures), with no effect on play.

## Changes from the draft (experiment spec, 21 Oct)

- Draft 4 ("walls, resting crates and water stop the player") was wrong about crates: a resting crate
  is pushed (rule 5) and stops the player only when it cannot move.
- Draft 5: the crate does not slide away on its own; the player pushes it the whole way and stops
  behind it. A crate that runs into other crates pushes them too (rule 6).
- Draft 6: the slide goes on after the crate sinks, and crates also slide over filled water.
- Added: no ACTION5 (rule 1), crossing the goal does not win (rule 8), water animation (rule 9).

## Evidence

### 1. Controls
- Source: line 5 `noaction`; the service lists only actions 1, 2, 3, 4, 7.
- Engine: level 1 `L U L U` moves the player left, up, left, up: (4,4) → (4,3) → (2,3) → (2,1) → (1,1).

### 2. Undo and restart
- Source: engine behaviour, not a game rule (`puzzlescript_interface/runtime/server.js` lines 457–481:
  one action runs all its `again` ticks, up to 50; RESET reloads the level).
- Engine: level 2 `U L` (player (4,6) → (2,6) → (2,1)), then `Z` → (2,6): one undo reverts the whole
  5-cell slide. `Z` → (4,6), the level start; a third `Z` changes nothing.
- Engine: level 4 `R D L U` (a crate sinks into the water at (3,4)), then `Z` → crate back on (5,4),
  water back on (3,4), player back on (6,4).
- Engine: a blocked move is an undo step too: level 1 `L L Z Z` → the first `Z` shows no change, the
  second puts the player back on (4,4).
- Engine: level 4 `R D L U Z U R`, then `RESET` → board identical to the level start.

### 3. Sliding
- Source: lines 356 and 362 (copies for the other directions at 364/370, 372/378, 380/386):
  `[ LEFT PlayerStill ] -> [ PlayerL ]`, `[ PlayerL ] -> [ LEFT PlayerL ] again`. The player moves one
  cell per tick until line 361 stops it.
- Engine: level 2 `L` from (2,6): one action returns 7 frames, player on (2,5), (2,4), (2,3), (2,2),
  (2,1), stopped by the wall at (2,0).

### 4. Walls and water stop the player
- Source: line 291 `Obstacle = Wall or StillCrate or Water`; line 361
  `LEFT [ PlayerL | Obstacle ] -> [ PlayerStill | Obstacle ]`; line 305 puts water on the player's
  collision layer.
- Engine: level 4 start, `L`: player (3,7) → (3,5), next to the water at (3,4).
- Engine: level 1 `L L`: the second `L` (wall right next to the player) changes nothing.

### 5. Pushing a crate
- Source: lines 357, 360, 361, 388: `LEFT [ PlayerL | Crate ] -> [ PlayerL | LEFT Crate ] again`,
  `LEFT [ > Crate | Obstacle ] -> [StillCrate | Obstacle]`, `[StillCrate]->[Crate]`. The crate moves
  only while the player pushes it, so the two move together.
- Engine: level 3 `L U L D L U` (player on (5,1)), then `R`: the player slides to (5,3); in the next
  tick crate (5,4) → (5,5) and player → (5,4); the crate stops at the wall (5,6), the player behind it.
- Engine: then `L R`: the player slides back and stops on (5,4); the crate, against the wall, does not
  move.
- Engine: then `L D R U`: per tick the crate goes (5,5) → (4,5) → (3,5) → (2,5) with the player one cell
  behind; both stop when the crate meets the wall at (1,5).

### 6. Rows of crates
- Source: line 358 `LEFT [ > Crate | Crate ] -> [ > Crate | > Crate ] again`.
- Engine: level 5 `D L U`: the touching pair (7,6), (8,6) moves up together (more under rule 7).
- Engine: level 6 `L U L U R D R U R U` (player (3,13), crate (3,12), resting pair (3,9), (3,10)), then
  `L`: the pushed crate reaches the pair and all three move left together; the front one sinks into
  the water at (3,6), the other two slide on to (3,3), (3,4) at the wall; the player stops on (3,5).
- Engine: level 4 `R D L D L U L D R D L U` (player on (5,7), next to the row (5,4)–(5,6), wall at
  (5,3)), then `L`: nothing moves.

### 7. Water and filled water
- Source: line 359 `LEFT [ > Crate | Water ] -> [ | FilledWater]`; FilledWater has its own layer
  (line 302) and is not an Obstacle (line 291).
- Engine: level 4 `R D L` (player on (6,4)), then `U`: tick 1 crate (5,4) → (4,4); tick 2 the crate
  disappears and (3,4) turns into filled water; the player goes on (4,4) → (3,4) → (2,4) → (1,4).
  Then `D`: the player slides down column 4, over the filled cell, to (8,4).
- Engine: level 5 `D L U`: the front crate fills (6,6); the back crate slides over (6,6) and the goal
  (5,6) and fills (4,6); the player slides on to (1,6).

### 8. Goal
- Source: line 395 `Some PlayerStill on Goal`; PlayerStill exists only while the player is at rest.
  Level 2's (skipped) message says "You must land ON the goal".
- Engine: level 1 `L U L U`: the player stops on the goal (1,1) → levels_completed 0 → 1.
- Engine: level 2 `U L`: the player crosses the goal (2,4) and stops on (2,1); levels_completed stays
  1. `D R U` then stops it on (2,4) (wall at (1,4)) → 2. Level 5 `D L U` also crosses the goal (5,6)
  without winning.

### 9. Water animation
- Source: lines 344–351, `[Water5]->[Water6]` … `[Water6]->[Water1]`, run every tick (and at level
  start, line 4); Water1 and Water6 share a sprite.
- Engine: level 5, `L` then `R`: the id of water cell (4,6) per tick is 10, 20, 21, 22, 23, 10, 20, …

## Full playthrough

A breadth-first solver built on rules 3–8 gives these shortest solutions (90 actions). Played on the
engine in one session from level 1, the board matched the solver's board cell for cell after every
move, each level ended on its last move, and the game ended `WIN` 6/6.

| level | actions | solution |
|---|---|---|
| 1 | 4 | `LULU` |
| 2 | 5 | `ULDRU` |
| 3 | 12 | `LULDLURLDRUR` |
| 4 | 29 | `LDLUDLULDRDRUDLULURDLDLURDRUL` |
| 5 | 8 | `DRULRDLU` |
| 6 | 32 | `LULURULULDULDRURDRURULULDULDRURD` |

## Not graded

- Walls take one of 16 textures depending on neighbouring walls (lines 318–341); all behave the same.
- While sliding, the player's sprite faces the slide direction (PlayerL/R/U/D); only mid-slide frames
  show it.
- The player or a crate on the goal looks the same as on plain floor.
