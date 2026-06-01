from __future__ import annotations

from pathlib import Path
from typing import Any

from client.engine.utils import format_grid


EVIDENCE_MODES = (
    "one_frame",
    "three_random_actions",
)

INPUT_MODES = (
    "text_only",
    "text_plus_first_image",
)

PROMPT_ID = "goal_recognition_v1"

SYSTEM_PROMPT = (
    "Infer the likely game goal from PuzzleScript/ARC observations. "
    "Return JSON only with these exact keys: goal_guess, "
    "win_condition_guess, key_objects, confidence, uncertainties, rationale."
)


def format_trajectory(trajectory: list[dict[str, Any]]) -> str:
    observations = []
    for index, item in enumerate(trajectory):
        text_grid = str(item.get("text_grid") or "").strip()
        if text_grid:
            grid_text = text_grid
        else:
            grid_text = format_grid(item.get("grid") or [])
        observations.append(
            f"Observation {index}\n"
            f"Action before observation: {item.get('action', 'unknown')}\n"
            f"Grid rows:\n{grid_text}"
        )
    return "\n\n".join(observations)


def build_prompt_variants(
    game_id: str,
    trajectory: list[dict[str, Any]],
    available_actions: list[str],
    first_image_path: Path | None = None,
    evidence_mode: str = "three_random_actions",
) -> dict[str, dict[str, Any]]:
    _ = game_id
    evidence = format_trajectory(trajectory)
    actions = ", ".join(available_actions) or "none"
    prompt_prefix = (
        "Use the text observations below.\n"
        "The actions are random, not a demonstrated solution.\n"
        "Grid symbols are visual ids: 0-9 keep their value; "
        "a=10, b=11, c=12, d=13, e=14, f=15.\n"
        f"Evidence mode: {evidence_mode}\n"
        f"Actions available after the final observation: {actions}\n\n"
        f"Trajectory:\n{evidence}"
    )

    prompts: dict[str, dict[str, Any]] = {}
    for input_mode in INPUT_MODES:
        image_paths = []
        input_note = ""
        if input_mode == "text_plus_first_image" and first_image_path is not None:
            image_paths = [str(first_image_path)]
            input_note = (
                "\n\nYou also receive the first rendered screenshot of the same game. "
                "Use it only as visual support for the numeric grid; do not infer from "
                "filename or path text."
            )

        prompt_suffix = (
            input_note
            + "\n\nQuestion:\n"
            "Infer the most likely plain-English game goal and success condition. "
            "Identify important visual ids, confidence, uncertainties, and a short rationale. "
            "Use goal_guess for the likely goal and win_condition_guess for the success condition. "
            "Use key_objects as an array of {value, role_guess} objects."
        )
        key = f"{evidence_mode}/{input_mode}/{PROMPT_ID}"
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_prefix,
                        "cache_control": {"type": "ephemeral", "ttl": "1h"},
                    },
                    {
                        "type": "text",
                        "text": prompt_suffix,
                    },
                ],
            },
        ]
        prompts[key] = {
            "evidence_mode": evidence_mode,
            "input_mode": input_mode,
            "prompt_id": PROMPT_ID,
            "system": SYSTEM_PROMPT,
            "prompt_prefix": prompt_prefix,
            "prompt_suffix": prompt_suffix,
            "prompt": prompt_prefix + prompt_suffix,
            "messages": messages,
            "cache_session_id": f"{game_id}:{evidence_mode}",
            "image_paths": image_paths,
        }
    return prompts
