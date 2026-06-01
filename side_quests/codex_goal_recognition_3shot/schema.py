from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GOAL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal_guess": {"type": "string"},
        "win_condition_guess": {"type": "string"},
        "key_objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "value": {"type": ["integer", "string"]},
                    "role_guess": {"type": "string"},
                },
                "required": ["value", "role_guess"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "number"},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": [
        "goal_guess",
        "win_condition_guess",
        "key_objects",
        "confidence",
        "uncertainties",
        "rationale",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class RunPaths:
    run_dir: Path
    manifest: Path
    sources: Path
    evidence: Path
    trajectories: Path
    prompts: Path
    batches: Path
    predictions: Path
    errors: Path
    skips: Path


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-openrouter-matrix")


def make_run_paths(out_dir: Path, run_id: str) -> RunPaths:
    run_dir = out_dir / run_id
    return RunPaths(
        run_dir=run_dir,
        manifest=run_dir / "manifest.json",
        sources=run_dir / "sources",
        evidence=run_dir / "evidence",
        trajectories=run_dir / "trajectories",
        prompts=run_dir / "prompts",
        batches=run_dir / "batches",
        predictions=run_dir / "predictions.jsonl",
        errors=run_dir / "errors.jsonl",
        skips=run_dir / "skips.jsonl",
    )


def frame_path_name(game_id: str) -> str:
    return game_id.replace("/", "_").replace("\\", "_") + ".json"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data) + "\n")


def clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_float(value: Any) -> float:
    if isinstance(value, str):
        label = value.strip().lower()
        if label == "low":
            return 0.25
        if label in {"moderate", "medium"}:
            return 0.5
        if label == "high":
            return 0.75
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def first_present(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data.get(key)
    return None


def normalize_key_objects(data: dict[str, Any]) -> list[dict[str, Any]]:
    key_objects = data.get("key_objects")
    if isinstance(key_objects, list):
        return [
            {
                "value": (
                    item.get("value", item.get("id", item.get("symbol", "")))
                    if isinstance(item, dict)
                    else item
                ),
                "role_guess": clean_string(
                    item.get("role_guess", item.get("role", item.get("description")))
                )
                if isinstance(item, dict)
                else "",
            }
            for item in key_objects
        ]

    object_map = (
        data.get("important_visual_ids")
        or data.get("important_ids")
        or data.get("visual_ids")
        or data.get("objects")
    )
    if isinstance(object_map, dict):
        return [
            {
                "value": value,
                "role_guess": clean_string(role),
            }
            for value, role in object_map.items()
        ]

    return []


def normalize_prediction(data: dict[str, Any]) -> dict[str, Any]:
    uncertainties = data.get("uncertainties")
    return {
        "goal_guess": clean_string(
            first_present(
                data,
                [
                    "goal_guess",
                    "goal",
                    "game_goal",
                    "likely_goal",
                    "likely_game_goal",
                    "inferred_goal",
                    "most_likely_goal",
                    "plain_english_goal",
                    "goal_hypothesis",
                    "goal_description",
                    "goal_plain_english",
                    "objective",
                    "goalGuess",
                    "answer",
                ],
            )
        ),
        "win_condition_guess": clean_string(
            first_present(
                data,
                [
                    "win_condition_guess",
                    "success_condition",
                    "win_condition",
                    "successCondition",
                    "winning_condition",
                    "success_criteria",
                    "goal_condition",
                    "success_condition_hypothesis",
                    "likely_success_condition",
                ],
            )
        ),
        "key_objects": normalize_key_objects(data),
        "confidence": clean_float(data.get("confidence")),
        "uncertainties": (
            uncertainties
            if isinstance(uncertainties, list)
            else ([clean_string(uncertainties)] if clean_string(uncertainties) else [])
        ),
        "rationale": clean_string(data.get("rationale")),
    }


def prediction_row(
    *,
    run_id: str,
    game_id: str,
    evidence_mode: str,
    input_mode: str,
    prompt_id: str,
    model: str,
    trajectory_path: Path,
    prompt_path: Path,
    raw_response: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "game_id": game_id,
        "evidence_mode": evidence_mode,
        "input_mode": input_mode,
        "prompt_id": prompt_id,
        "model": model,
        "trajectory_path": str(trajectory_path),
        "prompt_path": str(prompt_path),
        "prediction": normalize_prediction(raw_response),
        "manual_verification": None,
        "raw_response": raw_response,
    }


def error_row(
    *,
    run_id: str,
    game_id: str,
    error: Exception | str,
    evidence_mode: str | None = None,
    input_mode: str | None = None,
    prompt_id: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "game_id": game_id,
        "evidence_mode": evidence_mode,
        "input_mode": input_mode,
        "prompt_id": prompt_id,
        "model": model,
        "error": str(error),
    }
