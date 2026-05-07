import unittest

from client.live_sokoban.model import SymbolFrame, SymbolGoal
from client.live_sokoban.perceiver import SymbolPerceiver


SYMBOLS = {
    0: ".",
    1: "#",
    2: "P",
    3: "*",
    4: "@",
    5: "O",
}


class LivePerceptTests(unittest.TestCase):
    def test_perceiver_builds_symbol_facts_without_human_object_names(self) -> None:
        frame = SymbolPerceiver(SYMBOLS).from_grid(
            [
                [1, 2, 0],
                [5, 4, 3],
            ]
        )
        facts = frame.facts()

        self.assertIn("At(#,0,0)", facts)
        self.assertIn("At(P,1,0)", facts)
        self.assertIn("Empty(2,0)", facts)
        self.assertIn("Adjacent(1,0,2,0)", facts)
        self.assertNotIn("Player", "\n".join(facts))
        self.assertNotIn("Wall", "\n".join(facts))

    def test_star_goal_accepts_any_crate_bearing_symbol(self) -> None:
        goal = SymbolGoal(required_cells=((2, 1, "*"), (1, 3, "*")))
        unsolved = SymbolFrame.from_rows(
            [
                "###",
                "#O#",
                "#.#",
                "#@#",
            ]
        )
        solved = SymbolFrame.from_rows(
            [
                "###",
                "#O@",
                "#.#",
                "#@#",
            ]
        )
        solved_with_flat_crates = SymbolFrame.from_rows(
            [
                "###",
                "#O*",
                "#.#",
                "#*#",
            ]
        )

        self.assertFalse(goal.is_satisfied(unsolved))
        self.assertTrue(goal.is_satisfied(solved))
        self.assertTrue(goal.is_satisfied(solved_with_flat_crates))


if __name__ == "__main__":
    unittest.main()
