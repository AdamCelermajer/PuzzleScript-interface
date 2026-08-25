# Current-level working state

## Initial state (level 1)

- Grid is 7 rows x 6 columns. Coordinates below are zero-based `(row,col)`.
- Nonzero cells: `1` forms boundary/internal barriers; isolated values are `2` at
  `(3,2)`, `3` at `(4,3)`, `4` at `(3,1)`, and `5` at `(1,2)`.
- Hypothesis: `1` is wall and `2` is the controllable avatar. The values `3/4/5`
  may encode a movable object, a target, and an object already on a target, but this
  is explicitly unconfirmed.

## Diagnostic plan

- Move Right twice through cells currently encoded `0`. Prediction: if `2` is the
  avatar and `0` is traversable floor, it moves `(3,2)->(3,3)->(3,4)` and vacated
  cells become `0`; all other cells remain unchanged.
- This also positions the avatar conveniently for a later interaction test with
  value `3` at `(4,3)` if the hypothesis survives.

## After T000001-T000002

- Prediction matched exactly: avatar `2` is now at `(3,4)`.
- Next test: Down to `(4,4)`, then Left into value `3` at `(4,3)` with open cell
  `(4,2)` beyond it. If `3` is pushable, expected final row-4 segment is
  `... 3 at c2, 2 at c3, 0 at c4`; otherwise the Left action should be blocked.

## After T000003-T000004

- The push prediction matched exactly: `3` is now `(4,2)` and avatar `(4,3)`.
- Proposed completion route: Left pushes `3` to `(4,1)`; Down and Left route the
  avatar around to `(5,1)`; Up pushes `3` onto value `4` at `(3,1)`.
- Prediction: the occupied target becomes value `5`. Because another `5` exists
  at `(1,2)`, this likely completes the level (all target/object pairs occupied).

## After T000005-T000008

- First three transitions matched, leaving avatar `(5,1)` and `3` `(4,1)`.
- Up was blocked because value `4` occupied the intended destination beyond `3`.
  Thus the target interpretation of `4` is contradicted.
- Alternative goal test: route around the box via Right, Up, Up, Up to `(2,2)`,
  then Up into value `5` at `(1,2)`. Expected intermediate avatar positions:
  `(5,2),(4,2),(3,2),(2,2)`; the final interaction tests whether `5` is exit.

## After T000009-T000013

- Route matched. Entering `5` consumed it (cell became avatar `2`) but did not win.
- Likely key/door relation: `5` is a collectible and `4` the locked exit/door.
- Test route from avatar `(1,2)`: Down twice to `(3,2)`, then Left into `4` at
  `(3,1)`. If the collectible enabled `4`, this should open it or finish level 1.

## After T000014-T000016

- Leaving `(1,2)` restored value `5`; it is a persistent special floor/goal, not
  a collected item. The entry into `4` remained blocked.
- Avatar is now `(3,2)`, immediately right of `4` at `(3,1)`. This is an efficient
  position to test ACTION5 (Space/Action). Prediction is intentionally weak:
  ACTION5 may interact with adjacent `4`, alter the player/tool state, or do
  nothing. Any change will identify the missing mechanic without extra movement.

## After T000017

- ACTION5 did nothing. Current `3` position `(4,1)` is a deadlock, so RESET is
  deliberate.
- After reset, route Down `(4,2)`, Left `(4,1)`, Up attempts to push `4` from
  `(3,1)` to open `(2,1)`. This cleanly tests whether `4` is another pushable type.
- If successful, clearing `(3,1)` opens the loop needed to get below `3` after
  moving it to column 2, strongly suggesting the intended solution structure.

## After T000018-T000021

- Reset worked. The Up push transformed initial `4` at `(3,1)` into ordinary box
  `3` at `(2,1)` with avatar at `(3,1)`. Therefore `4` means box-on-goal.
- Current state: avatar `(3,1)`; boxes `(2,1)` and `(4,3)`; goals `(3,1)` and
  `(1,2)`.
- A BFS using only confirmed movement/pushing rules found a 30-action solution:
  `RRRDLULLDDRULURUULDRDDRRULDLUU`. It ends with boxes exactly on both goals.

## After T000022-T000041

- All 20 actions matched the BFS state transitions. T000040 additionally confirmed
  that pushing box `3` onto goal `5` produces box-on-goal `4`.
- Current exact state: avatar `(2,2)`, secured box-on-goal `(3,1)`, other box
  `(3,3)`, remaining goal `(1,2)`.
- The earlier prediction misstated the avatar as `(3,2)`; BFS and actual state put
  it at `(2,2)`. Object positions were correct.
- Remaining BFS suffix is `DDRRULDLUU` (10 actions), which routes right/below the
  free box, pushes it left to column 2, then pushes it upward twice onto `(1,2)`.

## Level 2 initial state (after T000051)

- Level 1 completed exactly as predicted.
- Level 2 is 7x6. Avatar `(2,3)`; ordinary box `(3,2)`; boxes-on-goals `(3,3)`
  and `(4,3)`; visible goal `(4,2)`; extra internal wall `(2,2)`.
- Using the confirmed rules, BFS found a 16-action solution:
  `RDDLRUULDUULLDDR`.
- Structure: move the lower box-on-goal left onto `(4,2)`; push the upper
  box-on-goal down into the vacated `(4,3)` goal; loop around the upper-left and
  push the ordinary box right onto `(3,3)`. This should complete the game.
