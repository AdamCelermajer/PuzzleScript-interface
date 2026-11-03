# Handoff after cp-020 (400 moves, level still 0/6)

- Vocabulary: player = "player"; red crate = "ring" (id 3), a "clockwise knight"; dark-blue target = "ball" (id 4), fixed at (3,6); dark-red marker at the landing cell = "red frame" (id 6); other landing option = "dashed circle" (id 5). Border = "brick border (impassable)".
- Controls: 1-4 = up/down/left/right, ACTION7 = perfect undo (also reverts a teleport), ACTION5 = "wait/tick" that resolves the 1-turn transient; it no longer ties ACTION5 to confirming anything (K1, K6 partial).
- Red crate: "ring moves +2 in E, +1 90deg clockwise from E"; player ends on the ring's old cell. Still insists it only ever goes clockwise (K3 partial, side wrong).
- Dashed circle: fitted as the counterclockwise knight destination ("the dashed shows the counterclockwise option") but treated as a cosmetic ghost; no idea of selecting with move keys (K5 partial, thinking only; notebook just calls it a transient).
- Refusal: "Off-board dest => move blocked"; nothing about landing cells occupied by walls or crates (K4 partial).
- Walls: notebook says the player is "blocked by border" (K2 partial; no orange crates seen).
- Wrong belief on the goal: "Ring can NEVER reach ball (3,6)", so it rules out ring-on-ball; notebook says the goal is "UNKNOWN" and lists H1-H4. It acts on H1 (win = some (player, ring) state) and is running a full 7 x 34 state sweep, about 85% done (K7 wrong, from thinking).
