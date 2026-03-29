"""Utility helpers shared across learning and solving pipelines."""
from typing import List

def format_grid(grid: List[List[int]]) -> str:
    """Format a 2D integer grid for LLM reading."""
    if not grid:
        return "[]"
    
    # Format with brackets but nice spacing, preserving the [0, 8, ...] style
    lines = []
    for row in grid:
        lines.append("  " + str(row))
    return "\n".join(lines)

def format_frames(frames: List[List[List[int]]]) -> str:
    """Format a 3D sequence of grids (ticks)."""
    if not frames:
        return "No frames"
    return "\n\n".join(f"Grid {i}:\n{format_grid(g)}" for i, g in enumerate(frames))

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
