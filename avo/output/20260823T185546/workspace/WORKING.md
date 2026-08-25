# Current-level working state

## Initial board (zero-indexed row,column)

- Non-0/1 cells: `5@(1,2)`, `4@(3,1)`, `2@(3,2)`, `3@(4,3)`.
- Connected apparent floor lies inside an irregular wall boundary. In particular,
  `(3,3)` is open immediately right of value 2.

## Hypotheses

1. Current player is `(5,1)`, value 3 is `(4,1)`, value 4 is `(3,1)`.
2. T000009 disproved the proposed 4-as-destination model: pushing 3 upward into
   4 did nothing.
3. The current placement of 3 against the left boundary is likely a deadlock
   for ordinary pushing, so resetting is preferable to spending moves escaping.
4. Value 5 at `(1,2)` is directly reachable in the initial board: player
   `(3,2)` -> Up `(2,2)` -> Up toward 5. It may be the level exit/goal.
5. Value 1 is probably impassable wall based on enclosure geometry, but has not
   been collision-tested.

## Next diagnostic

Record the contradiction, RESET the likely deadlocked level, then take two Up
moves to test direct player interaction with value 5. The first Up should move
the player to `(2,2)`; the second either reaches/triggers 5 or is blocked.
