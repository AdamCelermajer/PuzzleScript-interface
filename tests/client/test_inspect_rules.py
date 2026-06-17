import tempfile
import unittest
from pathlib import Path

from client.arc.types import GameAction, GameState
from client.engine.memory import EngineMemory
from client.engine.perception import EngineState
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
from client.engine.rulebook import Rulebook
from client.inspect_rules import build_report


def _state(grid: list[list[int]]) -> EngineState:
    return EngineState(
        grid=tuple(tuple(row) for row in grid),
        state=GameState.PLAYING,
        levels_completed=0,
        win_levels=1,
        game_id="debug-world",
    )


class InspectRulesTests(unittest.TestCase):
    def test_build_report_combines_rules_and_timeline_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "debug-world"
            memory = EngineMemory(base / "timeline.jsonl")
            transition = memory.record_transition(
                _state([[2, 0, 1]]), GameAction.ACTION4, _state([[0, 2, 1]])
            )
            rulebook = Rulebook(base)
            rulebook.add_generalized_rule(
                GeneralizedRule(
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
                    evidence_ids=(transition.id,),
                    summary="ACTION4 moves the player right into empty space.",
                )
            )

            report = build_report(base, recent=1)

            self.assertIn("Rules: 1", report)
            self.assertIn("Transitions: 1", report)
            self.assertIn("G000001 ACTION4 anchor=2", report)
            self.assertIn("ACTION4 moves the player right into empty space.", report)
            self.assertIn("IF cell(0,0)=2, cell(1,0)=0", report)
            self.assertIn("THEN set(0,0)=0, set(1,0)=2", report)
            self.assertIn(f"supports: {transition.id}", report)
            self.assertIn(f"{transition.id}: ACTION4", report)
            self.assertIn("Before:", report)
            self.assertIn("After:", report)


if __name__ == "__main__":
    unittest.main()
