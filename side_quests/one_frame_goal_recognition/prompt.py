from __future__ import annotations

from client.engine.utils import format_grid


def build_prompt(
    game_id: str,
    grid: list[list[int]],
    available_actions: list[str],
) -> tuple[str, str]:
    system = (
        "Goal recognition: infer the likely ARC game goal from numeric observations. Output JSON only."
    )
    prompt = (
        "Use only this one frame and action list. No hidden metadata, titles, "
        "source, or external hints.\n"
        "Grid symbols are visual ids, not names/colors. Legend: 0-9 keep their value; "
        "a=10, b=11, c=12, d=13, e=14, f=15.\n"
        f"Actions: {', '.join(available_actions) or 'none'}\n"
        f"Grid rows:\n{format_grid(grid)}\n\n"
        "JSON shape:\n"
        "{\n"
        '  "goal_guess": "short plain-English goal",\n'
        '  "win_condition_guess": "observable condition that would mean success",\n'
        '  "key_objects": [{"value": 2, "role_guess": "player"}],\n'
        '  "confidence": 0.0,\n'
        '  "uncertainties": ["what cannot be known from one frame"]\n'
        "}"
    )
    return system, prompt
