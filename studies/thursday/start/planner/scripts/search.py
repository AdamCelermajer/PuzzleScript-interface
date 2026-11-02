"""Shortest list of actions to a goal, from rules you write as Python code.

Usage:  python scripts/search.py rules.py
        python scripts/search.py --self-test

rules.py defines start() -> state (any hashable value), moves(state) -> [(action, next_state), ...]
and done(state) -> bool. The search is breadth-first, so the first solution found is a shortest one.
It plays nothing: it only reads your rules.
"""
import importlib.util
import sys
import time
from collections import deque
from pathlib import Path

MAX_STATES = 2_000_000
MAX_SECONDS = 120


def search(start, moves, done, max_states=MAX_STATES, max_seconds=MAX_SECONDS):
    """The shortest action list from start() to a done state, or None when there is none."""
    began = time.monotonic()
    first = start()
    if done(first):
        return []
    parent = {first: None}
    queue = deque([first])
    while queue:
        if time.monotonic() - began > max_seconds:
            raise RuntimeError(f"stopped after {max_seconds} s and {len(parent)} states without a solution")
        state = queue.popleft()
        for action, after in moves(state):
            if after in parent:
                continue
            parent[after] = (state, action)
            if done(after):
                path, node = [], after
                while parent[node] is not None:
                    node, step = parent[node]
                    path.append(step)
                return path[::-1]
            if len(parent) >= max_states:
                raise RuntimeError(f"stopped after {max_states} states without a solution")
            queue.append(after)
    return None


def load(path):
    path = Path(path).resolve()
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def self_test():
    # A corridor of cells 0..3: the goal is cell 3, reached in three moves right.
    path = search(lambda: 0, lambda s: [(a, s + d) for a, d in (("LEFT", -1), ("RIGHT", 1)) if 0 <= s + d <= 3],
                  lambda s: s == 3)
    assert path == ["RIGHT", "RIGHT", "RIGHT"], path
    assert search(lambda: 0, lambda s: [], lambda s: s == 3) is None
    print("self-test ok")


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test()
    if len(argv) != 2:
        raise SystemExit(__doc__)
    rules = load(argv[1])
    try:
        path = search(rules.start, rules.moves, rules.done)
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    if path is None:
        print("no solution")
    else:
        print(" ".join(str(action) for action in path) if path else "already done")


if __name__ == "__main__":
    main(sys.argv)
