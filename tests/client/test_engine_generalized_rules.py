import json
import tempfile
import unittest
from pathlib import Path

from client.engine.history import TransitionHistory
from client.engine.induction import RuleInducer
from client.engine.planner import Planner
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
from client.engine.rules import RuleLibrary
from client.engine.state import EngineState
from client.engine.types import GameAction, GameState
from client.engine.verifier import RuleVerifier


def _state(
    grid: list[list[int]], *, state: GameState = GameState.PLAYING
) -> EngineState:
    return EngineState(
        grid=tuple(tuple(row) for row in grid),
        state=state,
        levels_completed=1 if state == GameState.WIN else 0,
        win_levels=1,
        game_id="test-grid",
    )


def _verified_rule() -> GeneralizedRule:
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


class FakeJsonLlm:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, str, str]] = []

    def call_json(self, system: str, prompt: str, model_type: str = "flash") -> dict:
        self.calls.append((system, prompt, model_type))
        if not self.payloads:
            raise AssertionError("Unexpected LLM call")
        return self.payloads.pop(0)


class EngineGeneralizedRuleTests(unittest.TestCase):
    def test_rule_library_predicts_with_verified_generalized_rules_before_exact_memory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            library = RuleLibrary(Path(tmpdir))
            library.add_generalized_rule(_verified_rule())

            predictions = library.predict(_state([[1, 2, 0]]), GameAction.ACTION4)

            self.assertEqual([state.grid for state in predictions], [((1, 0, 2),)])

    def test_inducer_verifies_and_persists_llm_candidate_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = TransitionHistory(Path(tmpdir) / "transitions.jsonl")
            record = history.add(
                _state([[2, 0, 1]]), GameAction.ACTION4, _state([[0, 2, 1]])
            )
            library = RuleLibrary(Path(tmpdir))
            llm = FakeJsonLlm(
                [
                    {
                        "rules": [
                            {
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
                                "evidence_ids": [record.id],
                            }
                        ]
                    }
                ]
            )

            hypotheses = RuleInducer(
                llm, library, RuleVerifier(history)
            ).propose_from_recent("test-grid", [record])

            self.assertEqual(len(hypotheses), 1)
            self.assertEqual(library.generalized_rules[0].status, "verified")
            saved = json.loads((Path(tmpdir) / "rules_v2.json").read_text())
            self.assertEqual(saved["rules"][0]["status"], "verified")

    def test_inducer_logs_malformed_llm_output_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = TransitionHistory(Path(tmpdir) / "transitions.jsonl")
            record = history.add(
                _state([[2, 0, 1]]), GameAction.ACTION4, _state([[0, 2, 1]])
            )
            events: list[str] = []
            library = RuleLibrary(Path(tmpdir))
            llm = FakeJsonLlm([{"rules": [{"action": "ACTION4"}]}])

            hypotheses = RuleInducer(
                llm, library, RuleVerifier(history), event_sink=events.append
            ).propose_from_recent("test-grid", [record])

            self.assertEqual(hypotheses, [])
            self.assertIn("Rejected malformed rule candidate", events[0])

    def test_planner_uses_generalized_rules_before_llm_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = TransitionHistory(Path(tmpdir) / "transitions.jsonl")
            library = RuleLibrary(Path(tmpdir))
            library.add_generalized_rule(_verified_rule())
            planner = Planner(library, history, llm_client=FakeJsonLlm([]))
            current = _state([[2, 0]])
            predicted_win = _state([[0, 2]], state=GameState.WIN)
            library.add_generalized_rule(
                GeneralizedRule(
                    id="G000002",
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
                    evidence_ids=("T000002",),
                    status="verified",
                    result_state=predicted_win.state.value,
                    levels_completed=1,
                )
            )

            decision = planner.choose_action(
                current,
                frame_data=type(
                    "Frame",
                    (),
                    {"available_actions": [GameAction.ACTION4]},
                )(),
            )

            self.assertEqual(decision.reason, "verified_plan")
            self.assertEqual(decision.action, GameAction.ACTION4)


if __name__ == "__main__":
    unittest.main()
