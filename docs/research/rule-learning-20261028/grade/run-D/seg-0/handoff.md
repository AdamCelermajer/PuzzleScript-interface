# Handoff after cp-007 (129 moves, level 1 solved, now on level 2)

Notebook is still the cp-001 version (ACTION1-4 = moves, ACTION7 = undo, ACTION5 = commit; frozen-player toggle). All newer beliefs come from the thinking.

The model's own words: the red crate is the "ring" (bright = tile 3, the selected candidate = "dark ring" tile 6, the other candidate = "dashed ring" tile 5). The target is the "socket" (navy square with a green centre). A crate sitting on a target is the "fused tile" (tile 8). The cell the player entered is the "pad", and the pair of landing cells is the "bar".
- K3 (correct): when you step into a ring moving in direction D, the bar's centre is ring+2D. Its two ends are one cell to either side, perpendicular to D, and the dark ring starts at centre+rot90cw(D).
- K5/K6 (correct): while frozen, the arrow along the bar's axis moves the dark ring to the other end and the perpendicular arrows do nothing. A5 commits the bright ring there and frees the player.
- K4 (partial): it believes entry is allowed only if the centre ring+2D is in the field (wrong: it requires the centre to be grass or socket). An end on a fused tile is "suppressed": the dark ring starts at the other end and cannot flip. It is unsure whether ends on walls are allowed, and earlier it assumed both ends had to be valid.
- K2 (partial): it believes 0 tiles are brick walls, though it means to test walking onto them. It has seen no orange crates.
- K7 (partial): "the win condition is to commit the ring on top of the socket. Confirmed!" This is level-specific: it reads the fused tile as a decorative example and has no "every target" or "either crate kind".
- Wrong side-beliefs: a bar centre must be grass or socket; ACTION7 cannot undo a portal entry.
