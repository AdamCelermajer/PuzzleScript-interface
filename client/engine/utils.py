"""Utility helpers shared across learning and solving pipelines."""

from typing import Any, List


def _normalize_grid(grid: Any) -> List[List[int]]:
    if hasattr(grid, "tolist"):
        grid = grid.tolist()
    return [[int(value) for value in row] for row in grid]


def last_grid(frames: List[Any]) -> List[List[int]]:
    """Return the final settled grid from a frame stack."""
    if not frames:
        return []
    return _normalize_grid(frames[-1])


def format_grid(grid: List[List[int]]) -> str:
    """Format a 2D integer grid for LLM reading."""
    if not grid:
        return "[]"

    lines = []
    for row in grid:
        lines.append("  " + str(row))
    return "\n".join(lines)


def format_frames(frames: List[Any]) -> str:
    """Format only the final settled grid for LLM reading."""
    grid = last_grid(frames)
    if not grid:
        return "No frames"
    return format_grid(grid)


def extract_json(text: str) -> str:
    """Extract JSON content from markdown-fenced model responses."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    elif cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned[3:-3]
    return cleaned.strip()
