"""Utility helpers shared across learning and solving pipelines."""

import json
import re
from typing import Any, List


GRID_SYMBOLS = "0123456789abcdefghijklmnopqrstuvwxyz"


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
    """Format a 2D integer grid for compact LLM reading."""
    if not grid:
        return "[]"

    lines = []
    for row in grid:
        cells = []
        for value in row:
            if 0 <= value < len(GRID_SYMBOLS):
                cells.append(GRID_SYMBOLS[value])
            else:
                cells.append(f"{{{value}}}")
        lines.append("".join(cells))
    return "\n".join(lines)


def format_frames(frames: List[Any]) -> str:
    """Format only the final settled grid for LLM reading."""
    grid = last_grid(frames)
    if not grid:
        return "No frames"
    return format_grid(grid)


def extract_json(text: str) -> str:
    """Extract the first valid JSON object or array from a model response."""
    cleaned = text.strip()
    candidates = [cleaned]
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*([\s\S]*?)```",
            cleaned,
            flags=re.IGNORECASE,
        )
    )
    for candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character not in "[{":
            continue
        try:
            value, end = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return cleaned[index : index + end]
    return cleaned
