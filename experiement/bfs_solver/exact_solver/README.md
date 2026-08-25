# Certified exact PuzzleScript solver

This isolated experiment adds A* search on top of the complete-machine-state
adapter in the parent folder. It does not modify the PuzzleScript runtime or
benchmark service.

The solver uses only lower bounds selected from the parsed game file. When no
stronger template is certified, it falls back to `h=1` for unfinished states.
It also removes exact no-op actions and duplicate successor states.

Run one game:

```powershell
node experiement/bfs_solver/exact_solver/solve_game.js `
  --gameId ps_extra_push-v1 `
  --timeoutMs 60000 `
  --maxStates 250000
```

`visitedMode=exact` includes engine cache state and is the mode that reports
`optimalityProven=true`. `visitedMode=semantic` is useful for diagnosis and
reports only shortest-path status in the semantic merged-state graph.
`visitedMode=certified` is available only when the game-file analyzer proves a
supported behavioral quotient, such as the four-phase crate and target
animation cycles in The Art of Storage.

For rule-heavy games, `compiled_profiles.js` recognizes a narrow game/level
signature and compiles only the rule-relevant state. The compiled transition is
searched with the same exact A* termination rule, and every result is replayed
against the real PuzzleScript engine. The compiler is deliberately not a
generic approximation: an unmatched source falls back to complete machine
state search.

Run all nine old timeout cases:

```powershell
node experiement/bfs_solver/exact_solver/run_nine.js `
  --timeoutMs 180000 `
  --maxStates 5000000
```

Run one compiled case:

```powershell
node experiement/bfs_solver/exact_solver/solve_compiled_game.js `
  --gameId ps_side_painting-v1
```

The saved results are in `solutions.json`, with a readable summary in
`REPORT.md`.

Run the focused tests:

```powershell
node --test experiement/bfs_solver/exact_solver/*.test.js
```
