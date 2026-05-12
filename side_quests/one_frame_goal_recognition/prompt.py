from __future__ import annotations

from client.engine.utils import format_grid


def build_prompt(
    game_id: str,
    grid: list[list[int]],
    available_actions: list[str],
) -> tuple[str, str]:
    system = (
        "You are doing ARC goal recognition. Infer the likely objective from "
        "one numeric observation frame."
    )
    prompt = (
        "You see one frame from an unknown ARC environment.\n"
        "Use only the numeric grid and the available action names below.\n"
        "Do not use hidden metadata, title semantics, source files, or solution hints.\n"
        "Grid values are visual object or color ids, not object names.\n\n"
        f"Available actions: {', '.join(available_actions) or 'none'}\n"
        f"Numeric grid:\n{format_grid(grid)}\n\n"
        "Return JSON only with this shape:\n"
        "{\n"
        '  "goal_guess": "short plain-English goal",\n'
        '  "win_condition_guess": "observable condition that would mean success",\n'
        '  "key_objects": [{"value": 2, "role_guess": "player"}],\n'
        '  "confidence": 0.0,\n'
        '  "uncertainties": ["what cannot be known from one frame"]\n'
        "}"
    )
    return system, prompt
