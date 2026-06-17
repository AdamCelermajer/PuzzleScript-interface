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
        status="verified",
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
        self.assertEqual(rules[0].status, "candidate")

    def test_malformed_llm_rule_json_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required field"):
            candidate_rules_from_llm_json({"rules": [{"action": "ACTION4"}]})


if __name__ == "__main__":
    unittest.main()
