import unittest

from client.engine.types import GameAction
from client.live_sokoban_poc.model import BoardState, LEVEL1_TARGETS


LEVEL1_GRID = [
    [1, 1, 1, 1, 0, 0],
    [1, 0, 5, 1, 0, 0],
    [1, 0, 0, 1, 1, 1],
    [1, 4, 2, 0, 0, 1],
    [1, 0, 0, 3, 0, 1],
    [1, 0, 0, 1, 1, 1],
    [1, 1, 1, 1, 0, 0],
]


class BoardStateTests(unittest.TestCase):
    def test_converts_sokoban_level_one_grid_to_symbolic_board(self) -> None:
        board = BoardState.from_grid(LEVEL1_GRID)

        self.assertEqual(board.player, (2, 3))
        self.assertEqual(board.crates, frozenset({(1, 3), (3, 4)}))
        self.assertEqual(board.targets, LEVEL1_TARGETS)
        self.assertIn((0, 0), board.walls)
        self.assertEqual(board.cell_at((1, 3)), "crate_on_target")
        self.assertEqual(board.cell_at((2, 1)), "target")

        facts = board.facts()
        self.assertIn("At(Player,2,3)", facts)
        self.assertIn("At(Crate,1,3)", facts)
        self.assertIn("Wall(0,0)", facts)
        self.assertIn("Target(2,1)", facts)
        self.assertIn("Adjacent((2,3),RIGHT,(3,3))", facts)

    def test_goal_requires_crates_on_both_level_one_targets(self) -> None:
        board = BoardState.from_grid(LEVEL1_GRID)

        self.assertFalse(board.is_goal())

        solved = board.with_changes(
            player=(4, 4),
            crates=frozenset({(2, 1), (1, 3)}),
        )

        self.assertTrue(solved.is_goal())

    def test_apply_sokoban_action_updates_board_for_fake_environment(self) -> None:
        board = BoardState.from_grid(LEVEL1_GRID)

        moved = board.apply_sokoban_action(GameAction.ACTION2)
        pushed = moved.apply_sokoban_action(GameAction.ACTION4)

        self.assertEqual(moved.player, (2, 4))
        self.assertEqual(moved.crates, board.crates)
        self.assertEqual(pushed.player, (3, 4))
        self.assertIn((4, 4), pushed.crates)
        self.assertNotIn((3, 4), pushed.crates)


if __name__ == "__main__":
    unittest.main()
