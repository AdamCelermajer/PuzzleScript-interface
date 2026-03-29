"""
Executable rules for sokoban-basic.
Each function: (board, action) -> dict of expected changes, or None if rule doesn't apply.
"""

LEGEND = {"P": "player", "#": "wall", ".": "empty space", "*": "crate", "O": "target"}

DIR = {"W": (-1, 0), "A": (0, -1), "S": (1, 0), "D": (0, 1)}


def _parse(board_str):
    return [list(row) for row in board_str.strip().split("\n")]


def _at(grid, r, c):
    if 0 <= r < len(grid) and 0 <= c < len(grid[0]):
        return grid[r][c]
    return ""


def _find(grid, sym):
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell == sym:
                return r, c
    return None


# ── Movement ─────────────────────────────────────────────────────────

def move_into_empty(grid, action):
    """IF action is DIR AND '.' is in DIR of P THEN P moves DIR"""
    if action not in DIR:
        return None
    pos = _find(grid, "P")
    if not pos:
        return None
    dr, dc = DIR[action]
    nr, nc = pos[0] + dr, pos[1] + dc
    if _at(grid, nr, nc) != ".":
        return None
    return {pos: ".", (nr, nc): "P"}


def move_into_target(grid, action):
    """IF action is DIR AND 'O' is in DIR of P THEN P moves DIR"""
    if action not in DIR:
        return None
    pos = _find(grid, "P")
    if not pos:
        return None
    dr, dc = DIR[action]
    nr, nc = pos[0] + dr, pos[1] + dc
    if _at(grid, nr, nc) != "O":
        return None
    return {pos: ".", (nr, nc): "P"}


def push_crate(grid, action):
    """IF action is DIR AND '*' is in DIR of P AND '.' is beyond '*' THEN both move"""
    if action not in DIR:
        return None
    pos = _find(grid, "P")
    if not pos:
        return None
    dr, dc = DIR[action]
    cr, cc = pos[0] + dr, pos[1] + dc
    if _at(grid, cr, cc) != "*":
        return None
    br, bc = cr + dr, cc + dc
    if _at(grid, br, bc) not in (".", "O"):
        return None
    return {pos: ".", (cr, cc): "P", (br, bc): "*"}


# ── Collision ────────────────────────────────────────────────────────

def blocked_by_wall(grid, action):
    """IF action is DIR AND '#' is in DIR of P THEN P does not move"""
    if action not in DIR:
        return None
    pos = _find(grid, "P")
    if not pos:
        return None
    dr, dc = DIR[action]
    nr, nc = pos[0] + dr, pos[1] + dc
    if _at(grid, nr, nc) != "#":
        return None
    return {}  # empty dict = nothing changes


def push_blocked(grid, action):
    """IF action is DIR AND '*' is in DIR of P AND '#' is beyond '*' THEN P does not move"""
    if action not in DIR:
        return None
    pos = _find(grid, "P")
    if not pos:
        return None
    dr, dc = DIR[action]
    cr, cc = pos[0] + dr, pos[1] + dc
    if _at(grid, cr, cc) != "*":
        return None
    br, bc = cr + dr, cc + dc
    if _at(grid, br, bc) not in ("#", "*", ""):
        return None
    return {}  # blocked, nothing moves


# ── Engine ───────────────────────────────────────────────────────────

ALL_RULES = [move_into_empty, move_into_target, push_crate, blocked_by_wall, push_blocked]


def predict(board_str, action):
    """Run all rules, return the first matching prediction."""
    grid = _parse(board_str)
    for rule in ALL_RULES:
        result = rule(grid, action)
        if result is not None:
            return rule.__doc__, result
    return None, None


def verify(board_before, action, board_after):
    """Check if the transition matches any rule's prediction."""
    grid_before = _parse(board_before)
    grid_after = _parse(board_after)
    
    rule_name, predicted = predict(board_before, action)
    if predicted is None:
        return {"match": False, "reason": "no rule covers this transition"}

    # apply predicted changes to board_before
    expected = [row[:] for row in grid_before]
    for (r, c), sym in predicted.items():
        expected[r][c] = sym

    if expected == grid_after:
        return {"match": True, "rule": rule_name}
    else:
        return {"match": False, "rule": rule_name, "reason": "prediction doesn't match actual outcome"}


# ── Quick test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    board = "\n".join([
        "#####",
        "#P*.#",
        "#...#",
        "#####",
    ])

    # push crate right
    rule, changes = predict(board, "D")
    print(f"Action D: {rule}")
    print(f"Changes: {changes}\n")

    # blocked by wall going up  
    rule, changes = predict(board, "W")
    print(f"Action W: {rule}")
    print(f"Changes: {changes}\n")

    # move into empty going down
    rule, changes = predict(board, "S")
    print(f"Action S: {rule}")
    print(f"Changes: {changes}")