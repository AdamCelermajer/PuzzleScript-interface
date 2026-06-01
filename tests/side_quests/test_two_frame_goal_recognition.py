import json
import random
from pathlib import Path
from types import SimpleNamespace

from client.engine.types import ActionInput, FrameData, GameAction, GameState
from side_quests.two_frame_goal_recognition import run as run_module
from side_quests.two_frame_goal_recognition.prompt import build_prompt
from side_quests.two_frame_goal_recognition.run import (
    action_data,
    action_label,
    choose_action,
    normalize_prediction,
    parse_args,
    run_pending_games,
    write_result,
)


def frame_with_actions(actions: list[GameAction]) -> FrameData:
    return FrameData(
        frame=[[[0, 1], [2, 0]]],
        state=GameState.PLAYING,
        levels_completed=0,
        game_id="dummy",
        win_levels=1,
        guid="guid",
        full_reset=False,
        available_actions=actions,
        action_input=ActionInput(action=GameAction.RESET),
    )


def test_two_frame_prompt_is_goal_only_and_uses_compact_grids() -> None:
    system, prompt = build_prompt(
        game_id="ls20",
        trajectory=[
            {"action": "RESET", "grid": [[0, 11], [2, 0]]},
            {"action": "ACTION1", "grid": [[0, 11], [0, 2]]},
        ],
        available_actions=["ACTION1", "ACTION2"],
    )

    assert "goal recognition" in system.lower()
    assert "ls20" not in prompt
    assert "0b" in prompt
    assert "02" in prompt
    assert "[0, 11]" not in prompt
    assert '"goal_guess"' in prompt
    assert "confidence" not in prompt
    assert "win_condition" not in prompt


def test_normalize_prediction_keeps_goal_only() -> None:
    prediction = normalize_prediction(
        {
            "goal_guess": " Collect all dots. ",
            "confidence": 1,
            "win_condition_guess": "ignored",
        }
    )

    assert prediction == {"goal_guess": "Collect all dots."}


def test_choose_action_supports_click_only_games() -> None:
    assert choose_action(
        frame_with_actions([GameAction.ACTION6]),
        random.Random(1),
    ) == GameAction.ACTION6


def test_action_data_adds_click_coordinates() -> None:
    data = action_data(
        GameAction.ACTION6,
        frame_with_actions([GameAction.ACTION6]),
        random.Random(1),
    )

    assert data is not None
    assert 0 <= data["x"] < 2
    assert 0 <= data["y"] < 2
    assert action_label(GameAction.ACTION6, data).startswith("ACTION6 ")


def test_parse_args_defaults_to_25_games_and_ten_game_batches() -> None:
    args = parse_args(["--api-key", "arc-key"])

    assert args.limit == 25
    assert args.batch_size == 10


def test_write_result_separates_predictions_and_errors(tmp_path: Path) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    errors_path = tmp_path / "errors.jsonl"

    write_result(
        "prediction",
        {"game_id": "good", "prediction": {}},
        predictions_path,
        errors_path,
    )
    write_result(
        "error",
        {"game_id": "bad", "error": "boom"},
        predictions_path,
        errors_path,
    )

    assert json.loads(predictions_path.read_text(encoding="utf-8"))["game_id"] == "good"
    assert json.loads(errors_path.read_text(encoding="utf-8"))["game_id"] == "bad"


def test_run_pending_games_writes_each_completed_game(tmp_path: Path, monkeypatch) -> None:
    def fake_run_game_job(game_id, args, llm, frames_dir, prompts_dir):
        return "prediction", {"game_id": game_id, "prediction": {}}

    monkeypatch.setattr(run_module, "run_game_job", fake_run_game_job)
    predictions_path = tmp_path / "predictions.jsonl"
    errors_path = tmp_path / "errors.jsonl"

    run_pending_games(
        ["a", "b", "c"],
        SimpleNamespace(batch_size=2),
        object(),
        tmp_path / "frames",
        tmp_path / "prompts",
        predictions_path,
        errors_path,
    )

    rows = [
        json.loads(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
    ]
    assert {row["game_id"] for row in rows} == {"a", "b", "c"}
