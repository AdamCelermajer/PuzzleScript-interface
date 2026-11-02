"""Grid helpers."""
from typing import Any


def last_grid(frames: list[Any]) -> list[list[int]]:
    """The final settled grid of a frame stack."""
    if not frames:
        return []
    grid = frames[-1]
    if hasattr(grid, "tolist"):
        grid = grid.tolist()
    return [[int(value) for value in row] for row in grid]
