from game.grid import last_grid


def test_last_grid_returns_final_grid_only():
    assert last_grid([[[0, 1], [1, 0]], [[2, 3], [3, 2]]]) == [[2, 3], [3, 2]]
    assert last_grid([]) == []
