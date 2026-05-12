import json
from pathlib import Path

from side_quests.one_frame_goal_recognition.prompt import build_prompt
from side_quests.one_frame_goal_recognition.run import (
    completed_game_ids,
    normalize_prediction,
    write_jsonl,
)


def test_prompt_contains_grid_and_actions_without_game_identity() -> None:
    system, prompt = build_prompt(
        game_id="ls20",
        grid=[[0, 1], [2, 0]],
        available_actions=["ACTION1", "ACTION2"],
    )

    assert "goal recognition" in system.lower()
    assert "[0, 1]" in prompt
    assert "[2, 0]" in prompt
    assert "ACTION1" in prompt
    assert "ACTION2" in prompt
    assert "ls20" not in prompt
    assert "game source" not in prompt.lower()
    assert "readme" not in prompt.lower()
    assert "known solution" not in prompt.lower()


def test_normalize_prediction_keeps_expected_schema() -> None:
    prediction = normalize_prediction(
        {
            "goal_guess": " Reach the target. ",
            "win_condition_guess": "Player overlaps target.",
            "key_objects": [{"value": 2, "role_guess": "player"}],
            "confidence": "0.7",
            "uncertainties": ["one frame only"],
            "extra": "ignored",
        }
    )

    assert prediction == {
        "goal_guess": "Reach the target.",
        "win_condition_guess": "Player overlaps target.",
        "key_objects": [{"value": 2, "role_guess": "player"}],
        "confidence": 0.7,
        "uncertainties": ["one frame only"],
    }


def test_normalize_prediction_defaults_wrong_types() -> None:
    prediction = normalize_prediction(
        {
            "goal_guess": None,
            "win_condition_guess": None,
            "key_objects": "player",
            "confidence": "not-a-number",
            "uncertainties": "unclear",
        }
    )

    assert prediction == {
        "goal_guess": "",
        "win_condition_guess": "",
        "key_objects": [],
        "confidence": 0.0,
        "uncertainties": [],
    }


def test_completed_game_ids_reads_predictions_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    write_jsonl(path, {"game_id": "a", "prediction": {}})
    write_jsonl(path, {"game_id": "b", "prediction": {}})
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert completed_game_ids(path) == {"a", "b"}


def test_completed_game_ids_ignores_rows_without_game_id(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text(json.dumps({"prediction": {}}) + "\n", encoding="utf-8")

    assert completed_game_ids(path) == set()
