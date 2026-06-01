from __future__ import annotations

from client.engine.utils import format_grid


def build_prompt(
    game_id: str,
    trajectory: list[dict],
    available_actions: list[str],
) -> tuple[str, str]:
    _ = game_id
    system = (
        "Goal recognition: infer the likely ARC game goal from a random numeric trajectory. Output JSON only."
    )

    observations = []
    for index, item in enumerate(trajectory):
        observations.append(
            f"Observation {index}\n"
            f"Action before observation: {item['action']}\n"
            f"Grid rows:\n{format_grid(item['grid'])}"
        )

    prompt = (
        "Use only this random-action trajectory. Actions are random, not a solution.\n"
        "No hidden metadata, titles, source, README, or external hints.\n"
        "Grid symbols are visual ids, not names/colors. Legend: 0-9 keep their value; "
        "a=10, b=11, c=12, d=13, e=14, f=15.\n"
        f"Final actions: {', '.join(available_actions) or 'none'}\n\n"
        "Trajectory:\n"
        + "\n\n".join(observations)
        + "\n\nJSON shape:\n"
        "{\n"
        '  "goal_guess": "short plain-English goal",\n'
        '  "win_condition_guess": "observable condition that would mean success",\n'
        '  "key_objects": [{"value": 2, "role_guess": "player"}],\n'
        '  "confidence": 0.0,\n'
        '  "uncertainties": ["what cannot be known from this random trajectory"]\n'
        "}"
    )
    return system, prompt
