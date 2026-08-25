from __future__ import annotations

import json
from typing import Any


def frame_key(frame: list[list[int]]) -> str:
    return json.dumps(frame, separators=(",", ":"))


def score_frame_closeness(
    artifact: dict[str, Any],
    frame: list[list[int]],
    *,
    completed: bool,
) -> dict[str, Any]:
    if completed:
        return {
            "available": True,
            "closeness": 1.0,
            "percent": 100.0,
            "remaining_actions": 0,
            "basis": "level_completed",
        }
    lookup = {
        str(item["frame_key"]): item
        for item in artifact.get("trace", [])
    }
    match = lookup.get(frame_key(frame))
    if match is None:
        return {
            "available": False,
            "closeness": None,
            "percent": None,
            "remaining_actions": None,
            "basis": "off_saved_solution_trace",
        }
    value = float(match["closeness"])
    return {
        "available": True,
        "closeness": round(value, 6),
        "percent": round(value * 100, 2),
        "remaining_actions": int(match["remaining_actions"]),
        "basis": "replay_verified_solution_trace",
    }


def aggregate_closeness(
    games: list[dict[str, Any]],
) -> dict[str, Any]:
    available = [
        game["closeness"]["closeness"]
        for game in games
        if game["closeness"]["available"]
    ]
    return {
        "track": "closeness",
        "primary_metric": "mean_level_closeness",
        "games": games,
        "summary": {
            "mean_level_closeness": (
                round(sum(available) / len(available), 6)
                if available
                else None
            ),
            "available_games": len(available),
            "total_games": len(games),
            "coverage": (
                round(len(available) / len(games), 6) if games else 0.0
            ),
        },
    }
