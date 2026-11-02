from arcengine import GameAction

from client.play_arc_gui import cell_from_pixel, cell_size_for_grid, game_action_from_key


def test_cell_size_for_grid_keeps_large_boards_clickable() -> None:
    assert cell_size_for_grid(64, 64, max_width=960, max_height=720) >= 8


def test_cell_from_pixel_maps_canvas_position_to_grid_cell() -> None:
    assert cell_from_pixel(
        pixel_x=45,
        pixel_y=65,
        columns=10,
        rows=10,
        cell_size=10,
        origin_x=40,
        origin_y=60,
    ) == (0, 0)
    assert cell_from_pixel(
        pixel_x=69,
        pixel_y=89,
        columns=10,
        rows=10,
        cell_size=10,
        origin_x=40,
        origin_y=60,
    ) == (2, 2)


def test_cell_from_pixel_ignores_clicks_outside_grid() -> None:
    assert (
        cell_from_pixel(
            pixel_x=39,
            pixel_y=65,
            columns=10,
            rows=10,
            cell_size=10,
            origin_x=40,
            origin_y=60,
        )
        is None
    )


def test_game_action_from_key_maps_spacebar_to_action5() -> None:
    assert game_action_from_key(" ") == GameAction.ACTION5
