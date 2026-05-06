import unittest

from client.helped_live_sokoban.model import HelpedFrame, HelpedGoal


class HelpedModelTests(unittest.TestCase):
    def test_maps_rendered_values_to_puzzlescript_symbols(self) -> None:
        frame = HelpedFrame.from_grid([[0, 1, 2, 3, 4, 5]])

        self.assertEqual(frame.to_rows(), [".#P*@O"])

    def test_facts_include_symbols_empty_cells_and_adjacency(self) -> None:
        frame = HelpedFrame.from_grid([[4, 5, 0]])
        facts = frame.facts()

        self.assertIn("At(@,0,0)", facts)
        self.assertIn("At(O,1,0)", facts)
        self.assertIn("Empty(2,0)", facts)
        self.assertIn("Adjacent(0,0,1,0)", facts)
        self.assertFalse(any(fact.startswith("Base(") for fact in facts))

    def test_goal_checks_required_symbols(self) -> None:
        goal = HelpedGoal.from_cells([(2, 1, "@"), (1, 3, "@")])
        unsolved = HelpedFrame.from_grid(
            [
                [0, 0, 0],
                [0, 0, 5],
                [0, 0, 0],
                [0, 3, 0],
            ]
        )
        solved = HelpedFrame.from_grid(
            [
                [0, 0, 0],
                [0, 0, 4],
                [0, 0, 0],
                [0, 4, 0],
            ]
        )

        self.assertFalse(goal.is_satisfied(unsolved))
        self.assertTrue(goal.is_satisfied(solved))


if __name__ == "__main__":
    unittest.main()
