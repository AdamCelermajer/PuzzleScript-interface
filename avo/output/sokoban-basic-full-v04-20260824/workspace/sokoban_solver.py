from collections import deque


DIRS = [(-1, 0, "ACTION1"), (1, 0, "ACTION2"), (0, -1, "ACTION3"), (0, 1, "ACTION4")]


def solve(grid, goals):
    walls = {(r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v == 1}
    player = next((r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v == 2)
    boxes = frozenset((r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v in (3, 4))
    start = (player, boxes)
    q = deque([(start, [])])
    seen = {start}
    while q:
        (p, bs), path = q.popleft()
        if bs == frozenset(goals):
            return path, (p, bs), len(seen)
        for dr, dc, action in DIRS:
            np = (p[0] + dr, p[1] + dc)
            if np in walls:
                continue
            nbs = bs
            if np in bs:
                nb = (np[0] + dr, np[1] + dc)
                if nb in walls or nb in bs:
                    continue
                nbs = frozenset((bs - {np}) | {nb})
            ns = (np, nbs)
            if ns not in seen:
                seen.add(ns)
                q.append((ns, path + [action]))
    return None, None, len(seen)


if __name__ == "__main__":
    grid = [
        [1,1,1,1,0,0],
        [1,0,5,1,0,0],
        [1,0,0,1,1,1],
        [1,4,0,2,0,1],
        [1,0,0,3,0,1],
        [1,0,0,1,1,1],
        [1,1,1,1,0,0],
    ]
    print(solve(grid, {(1,2), (3,1)}))
