# Level 1

State (12 actions used): player(4,3), box(4,2), 4@(3,1), 5@(1,2). Undo worked as expected.

## Only possible win line (proved by geometry)
Box must enter (1,2)=5 via an UP push from (2,2), so box must travel up col2 from (4,2),
with player at (5,2) first. Player route (4,3)->(3,3)->(3,2)->(3,1)->(4,1)->(5,1)->(5,2)
passes through token 4 at (3,1). So the player must be able to step on 4 (else the puzzle
has a different goal entirely).

## Batch now: U, L, L
Expect player (3,3), (3,2), then attempt (3,1).
- If player enters (3,1): note whether 4 disappears (collectible) or persists.
- If no-op: rethink goal (maybe player must reach 5, and box/4 are obstacles).

## Continuation if L succeeds: D, D, R, U, U, U  (box to (1,2)=5)
