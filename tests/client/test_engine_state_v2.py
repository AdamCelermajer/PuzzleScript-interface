import unittest

from client.engine.state import EngineState
from client.engine.types import GameState


def _state(grid: list[list[int]]) -> EngineState:
    return EngineState(
        grid=tuple(tuple(row) for row in grid),
        state=GameState.PLAYING,
        levels_completed=0,
        win_levels=1,
        game_id="test-grid",
    )


class EngineStateV2Tests(unittest.TestCase):
    def test_symbol_positions_are_exposed_by_value(self) -> None:
        state = _state([[1, 0, 2], [2, 1, 0]])

        self.assertEqual(state.positions(2), ((2, 0), (0, 1)))
        self.assertEqual(state.positions(3), ())
        self.assertEqual(state.cell(1, 0), 0)
        self.assertIsNone(state.cell(4, 0))

    def test_changed_cells_between_states_are_reported(self) -> None:
        before = _state([[2, 0, 1], [0, 0, 1]])
        after = _state([[0, 2, 1], [0, 0, 1]])

        self.assertEqual(
            before.changed_cells(after),
            (
                {"x": 0, "y": 0, "before": 2, "after": 0},
                {"x": 1, "y": 0, "before": 0, "after": 2},
            ),
        )


if __name__ == "__main__":
    unittest.main()
