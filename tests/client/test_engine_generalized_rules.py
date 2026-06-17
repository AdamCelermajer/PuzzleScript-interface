import json
import tempfile
import unittest
from pathlib import Path

from client.engine.induction import RuleInducer
from client.engine.memory import EngineMemory
from client.engine.perception import EngineState, Perception
from client.engine.planner import Planner
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
from client.engine.rulebook import Rulebook
from client.arc.types import (
    ActionInput,
    FrameData,
    GameAction,
    GameState,
    RenderedFrame,
)
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
        available_actions=(GameAction.ACTION4,),
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
    )


class FakeJsonLlm:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def call_json(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> dict:
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "image_data_urls": list(image_data_urls or []),
                "purpose": purpose,
            }
        )
        if not self.payloads:
            raise AssertionError("Unexpected LLM call")
        return self.payloads.pop(0)


def _frame(grid: list[list[int]], image_url: str) -> FrameData:
    return FrameData(
        frame=[grid],
        state=GameState.PLAYING,
        levels_completed=0,
        game_id="test-grid",
        win_levels=1,
        guid="test-grid",
        full_reset=False,
        available_actions=[GameAction.ACTION4],
        action_input=ActionInput(action=GameAction.ACTION4),
        rendered_frame=RenderedFrame("image/png", image_url),
    )


class EngineGeneralizedRuleTests(unittest.TestCase):
    def test_rulebook_predicts_with_verified_generalized_rules_before_exact_memory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rulebook = Rulebook(Path(tmpdir))
            rulebook.add_generalized_rule(_verified_rule())

            predictions = rulebook.predict(_state([[1, 2, 0]]), GameAction.ACTION4)

            self.assertEqual([state.grid for state in predictions], [((1, 0, 2),)])

    def test_inducer_verifies_and_persists_llm_candidate_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            record = memory.record_transition(
                _state([[2, 0, 1]]), GameAction.ACTION4, _state([[0, 2, 1]])
            )
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeJsonLlm(
                [
                    {
                        "rules": [
                            {
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
                                "evidence_ids": [record.id],
                            }
                        ]
                    }
                ]
            )

            hypotheses = RuleInducer(
                llm, rulebook, RuleVerifier(memory)
            ).propose_from_recent("test-grid", [record])

            self.assertEqual(len(hypotheses), 1)
            self.assertEqual(
                rulebook.generalized_rules[0].summary,
                "ACTION4 moves the player one cell right into empty space.",
            )
            self.assertIn(
                "ACTION4 moves the player one cell right into empty space.",
                rulebook.known_rules_text(),
            )
            saved = json.loads((Path(tmpdir) / "rules.json").read_text())
            self.assertEqual(saved["rules"][0]["ruleID"], "G000001")
            self.assertNotIn("status", saved["rules"][0])
            self.assertEqual(saved["rules"][0]["evidence"]["supports"], [record.id])
            self.assertEqual(saved["rules"][0]["revision_count"], 0)
            self.assertFalse((Path(tmpdir) / "rules_v2.json").exists())
            self.assertFalse((Path(tmpdir) / "rules_v2.md").exists())
            self.assertFalse((Path(tmpdir) / "journal.md").exists())
            self.assertFalse((Path(tmpdir) / "journal_v2.md").exists())
            self.assertFalse((Path(tmpdir) / "rules.md").exists())

    def test_inducer_logs_malformed_llm_output_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            record = memory.record_transition(
                _state([[2, 0, 1]]), GameAction.ACTION4, _state([[0, 2, 1]])
            )
            events: list[str] = []
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeJsonLlm([{"rules": [{"action": "ACTION4"}]}])

            hypotheses = RuleInducer(
                llm, rulebook, RuleVerifier(memory), event_sink=events.append
            ).propose_from_recent("test-grid", [record])

            self.assertEqual(hypotheses, [])
            self.assertIn("Rejected malformed rule candidate", events[0])

    def test_inducer_sends_latest_memory_transition_images_to_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            before_image = "data:image/png;base64,before"
            after_image = "data:image/png;base64,after"
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            memory.record_transition(
                perception.perceive(_frame([[2, 0, 1]], before_image)),
                GameAction.ACTION4,
                perception.perceive(_frame([[0, 2, 1]], after_image)),
            )
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeJsonLlm([{"rules": []}])

            RuleInducer(llm, rulebook, RuleVerifier(memory)).propose_from_memory(
                "test-grid", memory
            )

            self.assertEqual(llm.calls[0]["image_data_urls"], [before_image, after_image])
            self.assertEqual(llm.calls[0]["purpose"], "rule creation")
            self.assertIn("Last memory transition", llm.calls[0]["prompt"])
            self.assertIn("ACTION4", llm.calls[0]["prompt"])
            self.assertIn('"anchor": {"value": 2}', llm.calls[0]["system"])
            self.assertIn('"offset": [1, 0]', llm.calls[0]["system"])

    def test_planner_uses_generalized_rules_before_llm_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            rulebook = Rulebook(Path(tmpdir))
            rulebook.add_generalized_rule(_verified_rule())
            predicted_win = _state([[0, 2]], state=GameState.WIN)
            rulebook.add_generalized_rule(
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
                    result_state=predicted_win.state.value,
                    levels_completed=1,
                )
            )
            memory.append_initial_state(_state([[2, 0]]))
            planner = Planner(
                rulebook=rulebook, memory=memory, llm_client=FakeJsonLlm([])
            )

            decision = planner.choose_action()

            self.assertEqual(decision.reason, "rule_plan")
            self.assertEqual(decision.action, GameAction.ACTION4)


if __name__ == "__main__":
    unittest.main()
