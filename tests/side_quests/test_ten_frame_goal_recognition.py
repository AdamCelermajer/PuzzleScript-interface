import random

from client.engine.types import ActionInput, FrameData, GameAction, GameState
from side_quests.ten_frame_goal_recognition.prompt import build_prompt
from side_quests.ten_frame_goal_recognition.run import (
    action_label,
    choose_random_action,
    normalize_prediction,
    random_action_data,
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


def test_choose_random_action_excludes_reset_and_undo_when_other_actions_exist() -> None:
    action = choose_random_action(
        frame_with_actions(
            [
                GameAction.RESET,
                GameAction.ACTION1,
                GameAction.ACTION6,
                GameAction.ACTION7,
            ]
        ),
        random.Random(1),
    )

    assert action == GameAction.ACTION1


def test_choose_random_action_falls_back_to_any_available_action() -> None:
    action = choose_random_action(
        frame_with_actions([GameAction.RESET, GameAction.ACTION7]),
        random.Random(1),
    )

    assert action in {GameAction.RESET, GameAction.ACTION7}


def test_choose_random_action_supports_click_only_games() -> None:
    assert choose_random_action(
        frame_with_actions([GameAction.ACTION6]),
        random.Random(1),
    ) == GameAction.ACTION6


def test_random_action_data_adds_click_coordinates() -> None:
    data = random_action_data(
        GameAction.ACTION6,
        frame_with_actions([GameAction.ACTION6]),
        random.Random(1),
    )

    assert data is not None
    assert 0 <= data["x"] < 2
    assert 0 <= data["y"] < 2
    assert action_label(GameAction.ACTION6, data).startswith("ACTION6 ")


def test_choose_random_action_returns_none_without_available_actions() -> None:
    assert choose_random_action(frame_with_actions([]), random.Random(1)) is None


def test_ten_frame_prompt_contains_actions_and_frames_but_not_game_id() -> None:
    system, prompt = build_prompt(
        game_id="ls20",
        trajectory=[
            {"action": "RESET", "grid": [[0, 1], [2, 0]]},
            {"action": "ACTION1", "grid": [[0, 1], [0, 2]]},
        ],
        available_actions=["ACTION1", "ACTION2"],
    )

    assert "goal recognition" in system.lower()
    assert "ls20" not in prompt
    assert "ACTION1" in prompt
    assert "ACTION2" in prompt
    assert "01" in prompt
    assert "[0, 1]" not in prompt
    assert "trajectory" in prompt.lower()


def test_normalize_prediction_matches_shared_schema() -> None:
    prediction = normalize_prediction({"goal_guess": "Collect all dots.", "confidence": 1})

    assert prediction["goal_guess"] == "Collect all dots."
    assert prediction["win_condition_guess"] == ""
    assert prediction["key_objects"] == []
    assert prediction["confidence"] == 1.0
    assert prediction["uncertainties"] == []
