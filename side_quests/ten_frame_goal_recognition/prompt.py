from __future__ import annotations

from client.engine.utils import format_grid


def build_prompt(
    game_id: str,
    trajectory: list[dict],
    available_actions: list[str],
) -> tuple[str, str]:
    _ = game_id
    system = (
        "You are evaluating goal recognition in ARC-AGI-3 games. "
        "Infer the likely game goal only from the provided random-action trajectory."
    )

    observations = []
    for index, item in enumerate(trajectory):
        observations.append(
            f"Observation {index}\n"
            f"Action before observation: {item['action']}\n"
            f"Frame:\n{format_grid(item['grid'])}"
        )

    prompt = (
        "You see a short random-action trajectory from an unknown ARC-AGI-3 game.\n"
        "Actions were random legal actions, not a solution attempt.\n"
        "Do not assume hidden source code, title semantics, README text, or known solutions.\n"
        "Numeric grid values are visual object/color ids, not labels.\n\n"
        f"Available actions after final observation: {', '.join(available_actions) or 'none'}\n\n"
        "Trajectory:\n"
        + "\n\n".join(observations)
        + "\n\nReturn JSON only with this shape:\n"
        "{\n"
        '  "goal_guess": "short plain-English goal",\n'
        '  "win_condition_guess": "observable condition that would mean success",\n'
        '  "key_objects": [{"value": 2, "role_guess": "player"}],\n'
        '  "confidence": 0.0,\n'
        '  "uncertainties": ["what cannot be known from this random trajectory"]\n'
        "}"
    )
    return system, prompt
