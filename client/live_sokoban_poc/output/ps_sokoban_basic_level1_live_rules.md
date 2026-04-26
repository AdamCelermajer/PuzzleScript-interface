# Sokoban LIVE Rule Model

Game: `ps_sokoban_basic-v1`, level 1
Goal: crates on `(2, 1)` and `(1, 3)`

## Active Rules

### R001 [active]
- action: `ACTION1`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 7
- emerged: At(Player,2,2), Empty(2,3), Occupied(2,2)
- vanished: At(Player,2,3), Empty(2,2), Occupied(2,3)

### R002 [active]
- action: `ACTION2`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 10
- emerged: At(Player,2,3), Empty(2,2), Occupied(2,3)
- vanished: At(Player,2,2), Empty(2,3), Occupied(2,2)

### R003 [active]
- action: `ACTION4`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 9
- emerged: At(Player,3,3), Empty(2,3), Occupied(3,3)
- vanished: At(Player,2,3), Empty(3,3), Occupied(2,3)

### R004 [active]
- action: `ACTION3`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 8
- emerged: At(Player,2,3), Empty(3,3), Occupied(2,3)
- vanished: At(Player,3,3), Empty(2,3), Occupied(3,3)

### R005 [active]
- action: `ACTION3`
- conditions: `FrontIsCrate, BehindCrateIsBlocked`
- effect: `blocked`
- plain_english: The move is blocked because a crate is in front of the player and the cell behind that crate is blocked.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 1
- emerged: -
- vanished: -

### R006 [active]
- action: `ACTION4`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 2
- emerged: At(Crate,4,4), At(Player,3,4), Empty(2,4), Occupied(4,4)
- vanished: At(Crate,3,4), At(Player,2,4), Empty(4,4), Occupied(2,4)

### R007 [active]
- action: `ACTION2`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 2
- emerged: At(Crate,1,4), At(Player,1,3), Empty(1,2), Occupied(1,4)
- vanished: At(Crate,1,3), At(Player,1,2), Empty(1,4), Occupied(1,2)

### R008 [active]
- action: `ACTION1`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 5
- emerged: At(Crate,1,3), At(Player,1,4), Empty(1,5), Occupied(1,3)
- vanished: At(Crate,1,4), At(Player,1,5), Empty(1,3), Occupied(1,5)

### R009 [active]
- action: `ACTION3`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 2
- emerged: At(Crate,2,4), At(Player,3,4), Empty(4,4), Occupied(2,4)
- vanished: At(Crate,3,4), At(Player,4,4), Empty(2,4), Occupied(4,4)


## Retired / Replaced Rules

(none)

## Prediction Failures

- exploration predicted False for ACTION1 from player (2, 3)
- exploration predicted False for ACTION2 from player (2, 2)
- exploration predicted False for ACTION4 from player (2, 3)
- exploration predicted False for ACTION3 from player (3, 3)
- exploration predicted False for ACTION3 from player (2, 3)
- exploration predicted False for ACTION4 from player (2, 4)
- exploration predicted False for ACTION2 from player (1, 2)
- exploration predicted False for ACTION1 from player (1, 5)
- exploration predicted False for ACTION3 from player (4, 4)

## Merge / Revision History

- created R001: move_player
- created R002: move_player
- created R003: move_player
- created R004: move_player
- created R005: blocked
- created R006: push_crate
- created R007: push_crate
- created R008: push_crate
- created R009: push_crate

## Rule Timeline

- created R001: move_player | active=[R001:move_player] | retired=[-]
- created R002: move_player | active=[R001:move_player, R002:move_player] | retired=[-]
- created R003: move_player | active=[R001:move_player, R002:move_player, R003:move_player] | retired=[-]
- created R004: move_player | active=[R001:move_player, R002:move_player, R003:move_player, R004:move_player] | retired=[-]
- created R005: blocked | active=[R001:move_player, R002:move_player, R003:move_player, R004:move_player, R005:blocked] | retired=[-]
- created R006: push_crate | active=[R001:move_player, R002:move_player, R003:move_player, R004:move_player, R005:blocked, R006:push_crate] | retired=[-]
- created R007: push_crate | active=[R001:move_player, R002:move_player, R003:move_player, R004:move_player, R005:blocked, R006:push_crate, R007:push_crate] | retired=[-]
- created R008: push_crate | active=[R001:move_player, R002:move_player, R003:move_player, R004:move_player, R005:blocked, R006:push_crate, R007:push_crate, R008:push_crate] | retired=[-]
- created R009: push_crate | active=[R001:move_player, R002:move_player, R003:move_player, R004:move_player, R005:blocked, R006:push_crate, R007:push_crate, R008:push_crate, R009:push_crate] | retired=[-]

## Final Rule Set

### R001 [active]
- action: `ACTION1`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 7
- emerged: At(Player,2,2), Empty(2,3), Occupied(2,2)
- vanished: At(Player,2,3), Empty(2,2), Occupied(2,3)

### R002 [active]
- action: `ACTION2`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 10
- emerged: At(Player,2,3), Empty(2,2), Occupied(2,3)
- vanished: At(Player,2,2), Empty(2,3), Occupied(2,2)

### R003 [active]
- action: `ACTION4`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 9
- emerged: At(Player,3,3), Empty(2,3), Occupied(3,3)
- vanished: At(Player,2,3), Empty(3,3), Occupied(2,3)

### R004 [active]
- action: `ACTION3`
- conditions: `FrontIsFree`
- effect: `move_player`
- plain_english: If the cell in front of the player is free, the player moves one cell in that direction.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 8
- emerged: At(Player,2,3), Empty(3,3), Occupied(2,3)
- vanished: At(Player,3,3), Empty(2,3), Occupied(3,3)

### R005 [active]
- action: `ACTION3`
- conditions: `FrontIsCrate, BehindCrateIsBlocked`
- effect: `blocked`
- plain_english: The move is blocked because a crate is in front of the player and the cell behind that crate is blocked.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 1
- emerged: -
- vanished: -

### R006 [active]
- action: `ACTION4`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 2
- emerged: At(Crate,4,4), At(Player,3,4), Empty(2,4), Occupied(4,4)
- vanished: At(Crate,3,4), At(Player,2,4), Empty(4,4), Occupied(2,4)

### R007 [active]
- action: `ACTION2`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 2
- emerged: At(Crate,1,4), At(Player,1,3), Empty(1,2), Occupied(1,4)
- vanished: At(Crate,1,3), At(Player,1,2), Empty(1,4), Occupied(1,2)

### R008 [active]
- action: `ACTION1`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 5
- emerged: At(Crate,1,3), At(Player,1,4), Empty(1,5), Occupied(1,3)
- vanished: At(Crate,1,4), At(Player,1,5), Empty(1,3), Occupied(1,5)

### R009 [active]
- action: `ACTION3`
- conditions: `FrontIsCrate, BehindCrateIsFree`
- effect: `push_crate`
- plain_english: If a crate is in front of the player and the cell behind that crate is free, the player pushes the crate one cell forward and moves into the crate's old cell.
- sibling: `-`
- retired_reason: `-`
- replacement: `-`
- source: observed transition
- applications: 2
- emerged: At(Crate,2,4), At(Player,3,4), Empty(4,4), Occupied(2,4)
- vanished: At(Crate,3,4), At(Player,4,4), Empty(2,4), Occupied(4,4)

