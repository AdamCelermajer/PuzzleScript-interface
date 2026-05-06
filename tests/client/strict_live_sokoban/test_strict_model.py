import tempfile
import unittest
from pathlib import Path

from client.engine.types import GameAction
from client.strict_live_sokoban.model import RawFrame, RawGoal
from client.strict_live_sokoban.rules import StrictRuleModel


START = [[2, 0, 0]]
AFTER_RIGHT = [[0, 2, 0]]
GOAL = [[0, 0, 2]]


class StrictModelTests(unittest.TestCase):
    def test_goal_is_raw_required_cells_only(self) -> None:
        goal = RawGoal(required_cells=((2, 0, 2),))

        self.assertFalse(goal.is_satisfied(RawFrame.from_grid(START)))
        self.assertTrue(goal.is_satisfied(RawFrame.from_grid(GOAL)))

    def test_rule_model_records_raw_transition_and_candidate_prediction(self) -> None:
        before = RawFrame.from_grid(START)
        after = RawFrame.from_grid(AFTER_RIGHT)
        model = StrictRuleModel()

        rule = model.observe(before, GameAction.ACTION4, after)
        predictions = model.predict(before, GameAction.ACTION4)

        self.assertEqual(rule.action, "ACTION4")
        self.assertEqual(rule.changed_cells, ((0, 0, 2, 0), (1, 0, 0, 2)))
        self.assertIn(after, predictions)

    def test_rule_file_names_limitations_without_sokoban_semantics(self) -> None:
        before = RawFrame.from_grid(START)
        after = RawFrame.from_grid(AFTER_RIGHT)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "strict_rules.md"
            model = StrictRuleModel(output_path=path)
            model.observe(before, GameAction.ACTION4, after)
            model.write(final=True)
            text = path.read_text(encoding="utf-8")

        self.assertIn("Strict Parameterless LIVE", text)
        self.assertIn("parameterless actions", text)
        self.assertIn("changed-cell hypothesis", text)
        self.assertNotIn("Player", text)
        self.assertNotIn("Crate", text)
        self.assertNotIn("Wall", text)
        self.assertNotIn("push", text.lower())

    def test_rule_model_persists_rules_for_later_experiments(self) -> None:
        before = RawFrame.from_grid(START)
        after = RawFrame.from_grid(AFTER_RIGHT)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "strict_rules.md"
            store_path = Path(tmpdir) / "strict_rules.json"
            first_model = StrictRuleModel(
                output_path=output_path,
                store_path=store_path,
            )
            first_model.observe(before, GameAction.ACTION4, after)

            second_model = StrictRuleModel(
                output_path=output_path,
                store_path=store_path,
            )

        self.assertIn(after, second_model.predict(before, GameAction.ACTION4))
        self.assertEqual(second_model.active_rules()[0].id, "R001")

    def test_rule_journal_keeps_append_only_growth_events(self) -> None:
        before = RawFrame.from_grid(START)
        after = RawFrame.from_grid(AFTER_RIGHT)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "strict_rules.md"
            journal_path = Path(tmpdir) / "strict_journal.md"
            model = StrictRuleModel(
                output_path=output_path,
                journal_path=journal_path,
            )
            model.observe(before, GameAction.ACTION4, after)
            model.record_prediction_result(
                before,
                GameAction.ACTION4,
                after,
                model.predict(before, GameAction.ACTION4),
            )
            journal = journal_path.read_text(encoding="utf-8")

        self.assertIn("created R001", journal)
        self.assertIn("prediction hit", journal)
        self.assertIn("changed_cells=((0, 0, 2, 0), (1, 0, 0, 2))", journal)

    def test_rule_model_learns_raw_action_delta_and_line_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = StrictRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                RawFrame.from_grid([[2, 3, 0]]),
                GameAction.ACTION4,
                RawFrame.from_grid([[0, 2, 3]]),
            )
            predictions = model.predict(
                RawFrame.from_grid([[0, 2, 3, 0]]),
                GameAction.ACTION4,
            )
            text = (Path(tmpdir) / "rules.md").read_text(encoding="utf-8")

        self.assertEqual(model.action_deltas[("ACTION4", 2)], (1, 0))
        self.assertIn(RawFrame.from_grid([[0, 0, 2, 3]]), predictions)
        self.assertIn("ActionDelta(ACTION4,2,1,0)", text)


if __name__ == "__main__":
    unittest.main()
