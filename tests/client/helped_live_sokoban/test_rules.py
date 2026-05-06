import tempfile
import unittest
from pathlib import Path

from client.engine.types import GameAction
from client.helped_live_sokoban.model import HelpedFrame
from client.helped_live_sokoban.rules import HelpedRuleModel


class HelpedRuleTests(unittest.TestCase):
    def test_learns_action_delta_from_occupant_motion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = HelpedRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                HelpedFrame.from_grid([[2, 0]]),
                GameAction.ACTION4,
                HelpedFrame.from_grid([[0, 2]]),
            )

        self.assertEqual(model.action_deltas[("ACTION4", "P")], (1, 0))

    def test_does_not_learn_direct_action_delta_from_pushed_occupant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = HelpedRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                HelpedFrame.from_grid([[2, 0, 0]]),
                GameAction.ACTION4,
                HelpedFrame.from_grid([[0, 2, 0]]),
            )
            model.observe(
                HelpedFrame.from_grid([[2, 3, 0]]),
                GameAction.ACTION4,
                HelpedFrame.from_grid([[0, 2, 3]]),
            )

        self.assertEqual(model.action_deltas[("ACTION4", "P")], (1, 0))
        self.assertNotIn(("ACTION4", "*"), model.action_deltas)

    def test_line_rules_move_symbols_without_base_layer_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = HelpedRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            before = HelpedFrame.from_rows(["P.."])
            after = HelpedFrame.from_rows([".P."])
            model.observe(before, GameAction.ACTION4, after)

            predictions = model.predict(
                HelpedFrame.from_rows(["P.."]),
                GameAction.ACTION4,
            )

        self.assertIn(HelpedFrame.from_rows([".P."]), predictions)

    def test_rule_file_describes_helped_representation_without_sokoban_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            model = HelpedRuleModel(
                output_path=output,
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                HelpedFrame.from_grid([[2, 0]]),
                GameAction.ACTION4,
                HelpedFrame.from_grid([[0, 2]]),
            )
            text = output.read_text(encoding="utf-8")

        self.assertIn("Helped LIVE Sokoban", text)
        self.assertIn("PuzzleScript symbol representation", text)
        self.assertIn("ActionDelta(ACTION4,P,1,0)", text)
        self.assertNotIn("base_", text)
        self.assertNotIn("Player", text)
        self.assertNotIn("Crate", text)
        self.assertNotIn("Wall", text)
        self.assertNotIn("push", text.lower())

    def test_generalizes_line_rule_across_learned_action_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = HelpedRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                HelpedFrame.from_grid([[2, 0, 0]]),
                GameAction.ACTION4,
                HelpedFrame.from_grid([[0, 2, 0]]),
            )
            model.observe(
                HelpedFrame.from_grid([[2], [0], [0]]),
                GameAction.ACTION2,
                HelpedFrame.from_grid([[0], [2], [0]]),
            )
            model.observe(
                HelpedFrame.from_grid([[2], [3], [0]]),
                GameAction.ACTION2,
                HelpedFrame.from_grid([[0], [2], [3]]),
            )

            predictions = model.predict(
                HelpedFrame.from_grid([[2, 3, 0]]),
                GameAction.ACTION4,
            )

        self.assertFalse(hasattr(model, "interaction_schemas"))
        self.assertIn(HelpedFrame.from_grid([[0, 2, 3]]), predictions)

    def test_cross_action_generalization_uses_anonymous_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = HelpedRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                HelpedFrame.from_signatures([["A", ".", "."]]),
                GameAction.ACTION4,
                HelpedFrame.from_signatures([[".", "A", "."]]),
            )
            model.observe(
                HelpedFrame.from_signatures([["A"], ["."], ["."]]),
                GameAction.ACTION2,
                HelpedFrame.from_signatures([["."], ["A"], ["."]]),
            )
            model.observe(
                HelpedFrame.from_signatures([["A"], ["X"], ["."]]),
                GameAction.ACTION2,
                HelpedFrame.from_signatures([["."], ["A"], ["X"]]),
            )

            predictions = model.predict(
                HelpedFrame.from_signatures([["A", "X", "."]]),
                GameAction.ACTION4,
            )

        self.assertIn(
            HelpedFrame.from_signatures([[".", "A", "X"]]),
            predictions,
        )

    def test_rule_file_shows_cross_action_generalizations_without_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            model = HelpedRuleModel(
                output_path=output,
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                HelpedFrame.from_grid([[2, 0, 0]]),
                GameAction.ACTION4,
                HelpedFrame.from_grid([[0, 2, 0]]),
            )
            model.observe(
                HelpedFrame.from_grid([[2], [0], [0]]),
                GameAction.ACTION2,
                HelpedFrame.from_grid([[0], [2], [0]]),
            )
            model.observe(
                HelpedFrame.from_grid([[2], [3], [0]]),
                GameAction.ACTION2,
                HelpedFrame.from_grid([[0], [2], [3]]),
            )
            text = output.read_text(encoding="utf-8")

        self.assertIn("Cross-Action Generalizations", text)
        self.assertIn("source_rule: R003", text)
        self.assertIn("target_action: ACTION4", text)
        self.assertNotIn("base_", text)
        self.assertNotIn("Induced Interaction Schemas", text)
        self.assertNotIn("schema", text.lower())
        self.assertNotIn("Player", text)
        self.assertNotIn("Crate", text)
        self.assertNotIn("Wall", text)
        self.assertNotIn("push", text.lower())


if __name__ == "__main__":
    unittest.main()
