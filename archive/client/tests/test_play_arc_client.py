from types import SimpleNamespace

from arcengine import GameAction

from client.play_arc_client import (
    action_is_available,
    key_to_action,
    mouse_position_from_key,
)


def test_mouse_position_from_sgr_click_sequence() -> None:
    assert mouse_position_from_key("\x1b[<0;12;8M") == (12, 8)


def test_mouse_position_ignores_release_sequence() -> None:
    assert mouse_position_from_key("\x1b[<0;12;8m") is None


def test_key_to_action_supports_coordinate_click_fallback() -> None:
    assert key_to_action("c") == "coordinate_click"


def test_key_to_action_maps_spacebar_to_action5() -> None:
    assert key_to_action(" ") == GameAction.ACTION5


def test_action_is_available_accepts_arcengine_actions() -> None:
    obs = SimpleNamespace(available_actions=[GameAction.ACTION6])

    assert action_is_available(obs, GameAction.ACTION6)


def test_action_is_available_accepts_numeric_arc_actions() -> None:
    obs = SimpleNamespace(available_actions=[6])

    assert action_is_available(obs, GameAction.ACTION6)
