# Handoff after cp-015 (267 moves, levels 1-3 solved, level 4 plan of 41 actions being executed)

The notebook is still the cp-001 version. All newer beliefs come from the thinking. Tile codes it uses: 0 brick, 1 grass, 2 player, 3 bright ring, 4 socket, 5/9 dashed ring on grass/socket, 6/7 dark ring on grass/socket, 8 cage.
- What it calls things: the red crate is the "ring". The target is the "socket". A red crate sitting on a target is the "cage" (tile 8). Stepping into a cage works like stepping into a ring: the ring is released and the socket shows again once the player leaves.
- K3 (correct): when you step into a ring or cage moving in direction D, the bar's centre C is R+2D. It now believes C can be any in-grid tile (brick, ring and cage centres were tested and work). The ends are C plus or minus rot90cw(D), and the dark ring starts at e1 = C+rot90cw(D).
- K4 (partial): an end is "suppressed" if it is brick, holds a ring or cage, or (its belief) is out of range. If e1 is suppressed the dark ring starts at e2, and it cannot flip onto a suppressed end. It no longer holds the old wrong belief that the centre must be grass or socket. Its account of refusal is still wrong: it says entry is blocked when the centre is off the grid. It has no clear "refused when no landing cell is free" (with both ends suppressed it says only that there is "no commit target").
- K5/K6 (correct): while frozen, the arrow towards the other end swaps dark and dashed. A5 commits: on grass the ring becomes bright, on a socket it becomes a cage. The player is released on the old ring tile.
- K7 (partial): "Cage all rings" (all rings committed onto sockets) is confirmed on levels 1-3. The rule is stated from the crates' side, and it does not mention crates of either kind.
- K2 (partial): brick is an impassable wall. It has seen no orange crates.
- Wrong side-belief: ACTION7 cannot undo a portal entry.
