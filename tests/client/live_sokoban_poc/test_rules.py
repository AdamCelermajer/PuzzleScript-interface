import tempfile
import unittest
from pathlib import Path

from client.engine.types import GameAction
from client.live_sokoban_poc.model import BoardState
from client.live_sokoban_poc.rules import Rule, RuleModel, RuleStatus


GRID = [
    [1, 1, 1, 1, 0, 0],
    [1, 0, 5, 1, 0, 0],
    [1, 0, 0, 1, 1, 1],
    [1, 4, 2, 0, 0, 1],
    [1, 0, 0, 3, 0, 1],
    [1, 0, 0, 1, 1, 1],
    [1, 1, 1, 1, 0, 0],
]


class RuleModelTests(unittest.TestCase):
    def test_creates_movement_rule_from_observed_transition(self) -> None:
        before = BoardState.from_grid(GRID)
        after = before.apply_sokoban_action(GameAction.ACTION2)
        model = RuleModel()

        rule = model.learn_from_transition(before, GameAction.ACTION2, after)
        prediction = model.predict(before, GameAction.ACTION2)

        self.assertEqual(rule.effect, "move_player")
        self.assertIn("FrontIsFree", rule.conditions)
        self.assertEqual(prediction.board, after)
        self.assertEqual(prediction.rule_id, rule.rule_id)

    def test_creates_push_rule_from_observed_transition(self) -> None:
        before = BoardState.from_grid(GRID).apply_sokoban_action(GameAction.ACTION2)
        after = before.apply_sokoban_action(GameAction.ACTION4)
        model = RuleModel()

        rule = model.learn_from_transition(before, GameAction.ACTION4, after)
        prediction = model.predict(before, GameAction.ACTION4)

        self.assertEqual(rule.effect, "push_crate")
        self.assertIn("FrontIsCrate", rule.conditions)
        self.assertIn("BehindCrateIsFree", rule.conditions)
        self.assertEqual(prediction.board, after)

    def test_creates_block_rule_from_noop_transition(self) -> None:
        before = BoardState.from_grid(GRID)
        after = before.apply_sokoban_action(GameAction.ACTION3)
        model = RuleModel()

        rule = model.learn_from_transition(before, GameAction.ACTION3, after)
        prediction = model.predict(before, GameAction.ACTION3)

        self.assertEqual(rule.effect, "blocked")
        self.assertIn("FrontIsCrate", rule.conditions)
        self.assertIn("BehindCrateIsBlocked", rule.conditions)
        self.assertEqual(prediction.board, before)

    def test_revises_over_general_rule_after_prediction_failure(self) -> None:
        before = BoardState.from_grid(GRID)
        actual = before.apply_sokoban_action(GameAction.ACTION3)
        model = RuleModel()
        faulty = model.add_rule(
            Rule(
                rule_id="",
                conditions=("Always",),
                action="ACTION3",
                effect="move_player",
                emerged=(),
                vanished=(),
                source="test seed",
            )
        )

        prediction = model.predict(before, GameAction.ACTION3)
        revised = model.revise_after_failure(faulty, before, GameAction.ACTION3, actual)

        self.assertNotEqual(prediction.board, actual)
        self.assertEqual(model.rules[faulty.rule_id].status, RuleStatus.RETIRED)
        self.assertEqual(model.rules[faulty.rule_id].retired_reason, "specialized_by")
        self.assertEqual(model.rules[faulty.rule_id].replacement_id, revised.rule_id)
        self.assertEqual(model.rules[faulty.rule_id].sibling_id, revised.rule_id)
        self.assertEqual(revised.sibling_id, faulty.rule_id)
        self.assertEqual(revised.effect, "blocked")

    def test_rule_file_keeps_active_retired_failure_and_final_rules(self) -> None:
        before = BoardState.from_grid(GRID)
        moved = before.apply_sokoban_action(GameAction.ACTION2)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "rules.md"
            model = RuleModel(output_path=output_path)
            move_rule = model.learn_from_transition(before, GameAction.ACTION2, moved)
            model.retire_rule(move_rule, reason="merged_into", replacement_id="R999")
            model.write_rule_file(final=True)

            text = output_path.read_text(encoding="utf-8")

        self.assertIn("# Sokoban LIVE Rule Model", text)
        self.assertIn("R001", text)
        self.assertIn("retired", text)
        self.assertIn("merged_into", text)
        self.assertIn("R999", text)
        self.assertIn("Rule Timeline", text)
        self.assertIn("Final Rule Set", text)


if __name__ == "__main__":
    unittest.main()
