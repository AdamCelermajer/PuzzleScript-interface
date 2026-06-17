import tempfile
import unittest
from pathlib import Path

from client.engine.memory import EngineMemory
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
from client.engine.perception import EngineState
from client.arc.types import GameAction, GameState
from client.engine.verifier import RuleVerifier


def _state(grid: list[list[int]]) -> EngineState:
    return EngineState(
        grid=tuple(tuple(row) for row in grid),
        state=GameState.PLAYING,
        levels_completed=0,
        win_levels=1,
        game_id="test-grid",
    )


def _candidate(evidence_ids: tuple[str, ...]) -> GeneralizedRule:
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
        evidence_ids=evidence_ids,
    )


class RuleVerifierTests(unittest.TestCase):
    def test_candidate_records_no_contradictions_when_it_predicts_cited_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            record = memory.record_transition(
                _state([[2, 0, 1]]), GameAction.ACTION4, _state([[0, 2, 1]])
            )

            result = RuleVerifier(memory).verify(_candidate((record.id,)))

            self.assertEqual(result.contradictions, ())

    def test_candidate_records_contradiction_without_rejecting_rule_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            record = memory.record_transition(
                _state([[2, 0, 1]]), GameAction.ACTION4, _state([[2, 0, 1]])
            )

            result = RuleVerifier(memory).verify(_candidate((record.id,)))

            self.assertIn(record.id, result.contradictions[0])


if __name__ == "__main__":
    unittest.main()
