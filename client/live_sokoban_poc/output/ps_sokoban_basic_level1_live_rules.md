# Sokoban LIVE Rule Model

Game: `ps_sokoban_basic-v1`, level 1
Goal: crates on `(2, 1)` and `(1, 3)`

## Active Rules

### R001 [active]
- action: `ANY_DIRECTION`
- conditions: `FrontIsCrate, BehindCrateIsBlocked`
- effect: `blocked`
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 1
- emerged: -
- vanished: -

### R002 [active]
- action: `ANY_DIRECTION`
- conditions: `FrontIsFree`
- effect: `move_player`
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 27
- emerged: At(Player,2,2), Empty(2,3), Occupied(2,2)
- vanished: At(Player,2,3), Empty(2,2), Occupied(2,3)

### R003 [active]
- action: `ANY_DIRECTION`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 9
- emerged: At(Crate,1,4), At(Player,1,3), Empty(1,2), Occupied(1,4)
- vanished: At(Crate,1,3), At(Player,1,2), Empty(1,4), Occupied(1,2)


## Retired / Replaced Rules

(none)

## Prediction Failures

- exploration predicted False for ACTION3 from player (2, 3)
- exploration predicted False for ACTION1 from player (2, 3)
- exploration predicted False for ACTION2 from player (1, 2)

## Merge / Revision History

- created R001: blocked
- created R002: move_player
- created R003: push_crate

## Rule Timeline

- created R001: blocked | active=[R001:blocked] | retired=[-]
- created R002: move_player | active=[R001:blocked, R002:move_player] | retired=[-]
- created R003: push_crate | active=[R001:blocked, R002:move_player, R003:push_crate] | retired=[-]

## Final Rule Set

### R001 [active]
- action: `ANY_DIRECTION`
- conditions: `FrontIsCrate, BehindCrateIsBlocked`
- effect: `blocked`
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 1
- emerged: -
- vanished: -

### R002 [active]
- action: `ANY_DIRECTION`
- conditions: `FrontIsFree`
- effect: `move_player`
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 27
- emerged: At(Player,2,2), Empty(2,3), Occupied(2,2)
- vanished: At(Player,2,3), Empty(2,2), Occupied(2,3)

### R003 [active]
- action: `ANY_DIRECTION`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 9
- emerged: At(Crate,1,4), At(Player,1,3), Empty(1,2), Occupied(1,4)
- vanished: At(Crate,1,3), At(Player,1,2), Empty(1,4), Occupied(1,2)

