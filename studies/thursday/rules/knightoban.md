# Knightoban (`ps_knightoban-v1`): true rules

The rule list for grading the players' `world.md`. Checked against
`puzzlescript_interface/games/ps_knightoban-v1/script.txt` and played on the local engine
(`http://127.0.0.1:8000`), 21 Oct 2026.

- **6 levels**: a tutorial, then Microban 1, 5, 6, 7 and 13 (the game's titles "0/5 (Tutorial)" to
  "5/5 (Microban 13)"). Actions offered: ACTION1–5 and ACTION7 (`available_actions: [1, 2, 3, 4, 5, 7]`).
- Notation: U D L R = ACTION1–4, X = ACTION5, Z = ACTION7. Cells are (row, column) in the level map as
  written in the script, (0, 0) top left. Level 1 (the tutorial) was played from a plain `RESET`;
  later levels were opened with `RESET` + `level_index` (levels 2–6 = indices 4, 6, 8, 10, 12), and all
  six were also played through in one session (end of file).

## Rules

1. ACTION1–4 move the player one cell up, down, left, right; ACTION5 does something only while a crate is lifted (rule 5).
2. ACTION7 undoes exactly one action (a step, a blocked move, lifting a crate, switching the choice or dropping the crate); RESET restarts the level.
3. Walls block the player.
4. Walking into a crate makes it jump like a chess knight: the player steps into the crate's cell and the crate is offered on the two squares two cells further on and one to either side; what lies in between does not matter, so a crate can even land outside the walls.
5. While a crate is lifted the player cannot move: the arrow pointing at the other offered square moves the selection there (the square on the player's right-hand side starts selected), and ACTION5 drops the crate on the selected square.
6. A knight square holding a wall or a crate is not offered: with one free square that is the only choice, and with none, walking into the crate does nothing.
7. The level is won when every target has a crate on it; a lifted crate does not count.

## Changes from the draft (experiment spec, 21 Oct)

- Draft 4 ("plain crates are pushed one cell, as in Sokoban") is dropped. The script defines a plain
  crate (`normalcrate`, line 125) but no level contains one (`&` and `!` never appear under LEVELS).
  Every crate is a knight crate, so "a pushed crate moves one cell" is a wrong rule in this game.
- Draft 5 made precise: only the two forward knight squares are offered, the player steps into the
  crate's cell and cannot move while choosing, and the square on its right starts selected.
- Added: undo works per action, each switch included (rule 2); ACTION5 does nothing otherwise
  (rule 1); with one free square that is the only choice (rule 6).

## Evidence

### 1. Controls
- Source: ACTION5 appears only in lines 135–136, which need the player to be choosing
  (`indicator_selecting`).
- Engine: tutorial `R` → player (3,2) → (3,3). `X` at the level start → board unchanged.

### 2. Undo and restart
- Source: engine behaviour, not a game rule (`puzzlescript_interface/runtime/server.js` lines 457–481).
- Engine: tutorial `R R U X` (crate dropped on (2,6)), then `Z` → crate lifted again with the selection
  on (2,6); `Z` → selection back on (4,6); `Z` → crate back on (3,4), player back on (3,3).
- Engine: tutorial `L L Z Z` → the first `Z` undoes the blocked `L` (no change), the second puts the
  player back on (3,2).
- Engine: tutorial `R R` (crate lifted), then `RESET` → board identical to the level start.

### 3. Walls
- Source: line 117 puts Player and Wall on the same collision layer.
- Engine: tutorial `L L`: (3,2) → (3,1), then the wall at (3,0) blocks the second `L`.

### 4. Knight jump
- Source: line 127 `[> player no indicator| Crate | | ] -> [ | player indicator_placing | | > knight_marker]`
  moves the player into the crate's cell, removes the crate and puts a marker two cells beyond it;
  lines 129–130 put a possible crate on each side of the marker.
- Engine: tutorial `R R`: player (3,3) → (3,4), the crate disappears, and outlines appear on (2,6) and
  (4,6): two cells right of (3,4) and one up or down.
- Engine: level 3 (Microban 5) start, `L`: crate (3,3) is offered (4,1), although the cell two to the
  left, (3,1), is a wall.
- Engine: level 2 (Microban 1) `R D X`: crate (4,3) jumps over the bottom wall to (6,4), floor outside
  the room (the level can then no longer be solved).

### 5. Choosing and placing
- Source: line 139 (one possible crate becomes the selected one), lines 141–144 (an arrow moves the
  selection along its line), line 146 (the player's move is cancelled while choosing), lines 135–136
  (ACTION5 removes the other choice and turns the selected one into a crate).
- Engine: tutorial `R R`: selected (4,6) (solid outline), other choice (2,6) (dotted). `L R D D`:
  nothing changes, the player stays on (3,4). `U`: the selection moves to (2,6).
- Engine: tutorial `R R U X`: the crate lands on (2,6). After a drop the arrows move the player again
  (`R R D X U` → crate on (4,6), player (3,4) → (2,4)).
- Engine: in all 21 two-choice pushes of the full playthrough, the square on the player's right-hand
  side started selected: walking right → lower, left → upper, up → right, down → left.

### 6. Blocked knight squares
- Source: line 96 `object = Crate or wall or player or normalcrate`; lines 129–130 need `no object`;
  with no possible crate, lines 132–133 (`[indicator_placing] -> cancel`) cancel the whole move.
- Engine: tutorial `R R U X U R` (crate on (2,6), player on (2,5)), then `R`: nothing changes (the
  squares (1,8), (3,8) are walls). Then `D R U` (into the crate from below): nothing changes (squares
  (0,5), (0,7) are walls).
- Engine: level 2 `D L U`: crate (3,1) is offered only (1,2) (the other square, (1,0), is a wall), and
  it starts selected. Level 3 `L`: only (4,1); `U D L R` change nothing; `X` drops the crate on (4,1).

### 7. Win
- Source: line 154 `All Target on crates`, with `crates = Crate or normalcrate` (line 97); the outlines
  of a lifted crate are other objects and do not count.
- Engine: tutorial `U R R D R X D R R D L X L L U X U U R X`: the last `X` drops the crate on the target
  (3,6) → levels_completed 0 → 1.
- Engine: level 2 starts with a crate on the target (3,1) and an empty target (1,2): `D L U X` moves
  that crate onto (1,2) (still 1), `R R R D L X` puts the other crate on (3,1) → 2.

## Full playthrough

Solutions from a breadth-first solver built on rules 3–7 (164 actions; it counts steps and jumps, so
they are not necessarily shortest in actions). Played on the engine in one session from level 1: for
all 34 jumps the offered squares matched the solver's, the board matched cell for cell after every
move, each level ended on its last move, and the game ended `WIN` 6/6.

| level | actions | solution |
|---|---|---|
| 1 Tutorial | 20 | `U R R D R X D R R D L X L L U X U U R X` |
| 2 Microban 1 | 10 | `D L U X R R R D L X` |
| 3 Microban 5 | 33 | `L X D D L L U X D R R R U X R R U L X R U U L L D R X U L L D R X` |
| 4 Microban 6 | 41 | `U L L D L L L L L D X D D L U X D L U X U U R X R X L D R X D D R U X U U R X R X` |
| 5 Microban 7 | 32 | `U U L X L L U U U R R D R X R D X R D D L X D L L U X L U U R X` |
| 6 Microban 13 | 28 | `D D X D D D R U X U X L U L X U X U R D X D D D L U L X` |

## Not graded

- The plain crate (`normalcrate`, orange) and its one-cell push (line 125): never in a level.
- The player standing on a target hides it (same texture as on plain floor).
