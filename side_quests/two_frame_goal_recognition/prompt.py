from __future__ import annotations

from typing import Any

from client.engine.utils import format_grid


def build_prompt(
    game_id: str,
    trajectory: list[dict[str, Any]],
    available_actions: list[str],
) -> tuple[str, str]:
    system = "Goal recognition: infer the likely ARC game goal. Output JSON only."
    observations = []
    for index, item in enumerate(trajectory):
        action = item.get("action", "unknown")
        grid = item.get("grid") or []
        observations.append(
            f"Observation {index} after {action}:\n{format_grid(grid)}"
        )

    prompt = (
        "Use only these two observations and the action list. No hidden metadata, "
        "titles, source, object names, colors, or external hints.\n"
        "Grid symbols are visual ids. Legend: 0-9 keep their value; "
        "a=10, b=11, c=12, d=13, e=14, f=15.\n"
        f"Actions now available: {', '.join(available_actions) or 'none'}\n\n"
        + "\n\n".join(observations)
        + "\n\nJSON shape:\n"
        "{\n"
        '  "goal_guess": "short plain-English game goal"\n'
        "}"
    )
    return system, prompt
