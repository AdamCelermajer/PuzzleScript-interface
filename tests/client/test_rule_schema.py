import unittest

from client.engine.rule_schema import (
    CellCondition,
    CellEffect,
    GeneralizedRule,
    candidate_rules_from_llm_json,
)
from client.engine.perception import EngineState
from client.arc.types import GameAction, GameState


def _state(grid: list[list[int]]) -> EngineState:
    return EngineState(
        grid=tuple(tuple(row) for row in grid),
        state=GameState.PLAYING,
        levels_completed=0,
        win_levels=1,
        game_id="test-grid",
    )


def _move_right_rule() -> GeneralizedRule:
    return GeneralizedRule(
        id="G000001",
        action="ACTION4",
        anchor=2,
        conditions=(
            CellCondition(dx=0, dy=0, value=2),
            CellCondition(dx=1, dy=0, value=0),
        ),
        effects=(
            CellEffect(dx=0, dy=0, value=0),
            CellEffect(dx=1, dy=0, value=2),
        ),
        evidence_ids=("T000001",),
    )


class RuleSchemaTests(unittest.TestCase):
    def test_rule_applies_to_matching_board(self) -> None:
        predictions = _move_right_rule().predict(_state([[2, 0, 1]]))

        self.assertEqual([state.grid for state in predictions], [((0, 2, 1),)])

    def test_rule_generalizes_to_translated_board(self) -> None:
        predictions = _move_right_rule().predict(_state([[1, 2, 0]]))

        self.assertEqual([state.grid for state in predictions], [((1, 0, 2),)])

    def test_rule_does_not_apply_when_condition_is_missing(self) -> None:
        predictions = _move_right_rule().predict(_state([[2, 1, 0]]))

        self.assertEqual(predictions, [])

    def test_llm_rule_json_parses_to_executable_schema(self) -> None:
        data = {
            "rules": [
                {
                    "id": "llm-move-right",
                    "summary": "ACTION4 moves the player one cell right into empty space.",
                    "action": "ACTION4",
                    "anchor": 2,
                    "conditions": [
                        {"dx": 0, "dy": 0, "value": 2},
                        {"dx": 1, "dy": 0, "value": 0},
                    ],
                    "effects": [
                        {"dx": 0, "dy": 0, "value": 0},
                        {"dx": 1, "dy": 0, "value": 2},
                    ],
                    "evidence_ids": ["T000001"],
                }
            ]
        }

        rules = candidate_rules_from_llm_json(data)

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].action, GameAction.ACTION4.name)
        self.assertEqual(
            rules[0].summary,
            "ACTION4 moves the player one cell right into empty space.",
        )
        self.assertEqual(rules[0].contradictions, ())
        self.assertEqual(rules[0].revision_count, 0)

    def test_llm_rule_json_accepts_structured_logical_rule_shape(self) -> None:
        data = {
            "rules": [
                {
                    "summary": "ACTION4 moves the player one cell right into empty space.",
                    "action": "ACTION4",
                    "anchor": {"value": 2},
                    "conditions": [
                        {"offset": [0, 0], "equals": 2},
                        {"offset": [1, 0], "equals": 0},
                    ],
                    "effects": [
                        {"offset": [0, 0], "set": 0},
                        {"offset": [1, 0], "set": 2},
                    ],
                    "evidence_ids": ["T000001"],
                }
            ]
        }

        rules = candidate_rules_from_llm_json(data)

        self.assertEqual(rules[0].anchor, 2)
        self.assertEqual(rules[0].conditions[1].dx, 1)
        self.assertEqual(rules[0].effects[1].value, 2)

    def test_legacy_rule_data_accepts_structured_anchor_and_offsets(self) -> None:
        rule = GeneralizedRule.from_data(
            {
                "id": "G000001",
                "summary": "ACTION4 moves the player right.",
                "action": "ACTION4",
                "anchor": {"value": 2},
                "conditions": [
                    {"offset": [0, 0], "equals": 2},
                    {"offset": [1, 0], "equals": 0},
                ],
                "effects": [
                    {"offset": [0, 0], "set": 0},
                    {"offset": [1, 0], "set": 2},
                ],
                "evidence_ids": ["T000001"],
            }
        )

        self.assertEqual(rule.anchor, 2)
        self.assertEqual(rule.conditions[1].dx, 1)
        self.assertEqual(rule.effects[1].value, 2)

    def test_malformed_llm_rule_json_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required field"):
            candidate_rules_from_llm_json({"rules": [{"action": "ACTION4"}]})


if __name__ == "__main__":
    unittest.main()
