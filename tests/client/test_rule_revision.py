import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from client.arc.types import GameAction, GameState
from client.engine.induction import NaturalRuleHypothesis, RuleLearner
from client.engine.memory import EngineMemory
from client.engine.natural_rules import NaturalRuleLibrary, RuleFailureLog
from client.engine.perception import EngineState
from client.engine.revision import RevisionCompilationResult
from client.engine.rule_attempts import RuleAttemptLog
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
from client.engine.rulebook import Rulebook
from client.engine.verifier import RuleVerifier
from client.engine.planner import PlanDecision
from client.runtime.runner import RuleReasoningLoop


def state(values):
    return EngineState(
        grid=(tuple(values),),
        state=GameState.PLAYING,
        levels_completed=0,
        win_levels=1,
        game_id="revision-test",
    )


def move_rule(evidence_id):
    return GeneralizedRule(
        id="",
        action="ACTION4",
        anchor=2,
        conditions=(
            CellCondition(0, 0, 2),
            CellCondition(1, 0, 0),
        ),
        effects=(CellEffect(0, 0, 0), CellEffect(1, 0, 2)),
        evidence_ids=(evidence_id,),
        summary="ACTION4 moves the player right when the next cell is empty.",
    )


def push_rule(evidence_id):
    return GeneralizedRule(
        id="",
        action="ACTION4",
        anchor=2,
        conditions=(
            CellCondition(0, 0, 2),
            CellCondition(1, 0, 3),
            CellCondition(2, 0, 0),
        ),
        effects=(
            CellEffect(0, 0, 0),
            CellEffect(1, 0, 2),
            CellEffect(2, 0, 3),
        ),
        evidence_ids=(evidence_id,),
        summary="ACTION4 pushes a crate right when the cell beyond it is empty.",
    )


class StaticReviser:
    def __init__(self, rules):
        self.rules = tuple(rules)
        self.llm_client = SimpleNamespace(cfg=SimpleNamespace(model="test/model"))

    def revise(self, *_args, **_kwargs):
        return RevisionCompilationResult(
            logical_rules=self.rules,
            raw_response='{"rules": [{"summary": "revision"}]}',
            parsed_response={"rules": [{"summary": "revision"}]},
            system_prompt="revision system",
            user_prompt="revision prompt",
        )


class RuleRevisionTests(unittest.TestCase):
    def test_runtime_routes_contradictions_to_revision(self):
        calls = []

        class Learner:
            def revise_from_memory(self, rule_ids, memory, **kwargs):
                calls.append(("revise", list(rule_ids), memory))
                return "revision_complete"

            def learn_from_memory(self, *_args, **_kwargs):
                calls.append(("learn", [], None))
                return "learning_complete"

        loop = object.__new__(RuleReasoningLoop)
        loop.engine = object()
        loop.inducer = Learner()
        loop.memory = object()
        loop.stop_event = threading.Event()
        loop.legend = {2: "Player"}
        decision = PlanDecision(GameAction.ACTION4, "test", [GameAction.ACTION4])

        result = loop._maybe_learn(
            "revision-test",
            decision=decision,
            contradicted=True,
            unexplained=False,
            contradicted_rule_ids=["G000001"],
        )

        self.assertEqual(result, "revision_complete")
        self.assertEqual(calls[0][0:2], ("revise", ["G000001"]))

    def test_contradiction_supersedes_old_natural_and_logical_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            memory.append_initial_state(state([2, 0]))
            old_transition = memory.append_action_result(
                GameAction.ACTION4, state([0, 2])
            )

            rulebook = Rulebook(base)
            broad_old = GeneralizedRule(
                id="",
                action="ACTION4",
                anchor=2,
                conditions=(CellCondition(0, 0, 2),),
                effects=(CellEffect(0, 0, 0), CellEffect(1, 0, 2)),
                evidence_ids=(old_transition.id,),
                summary="ACTION4 always moves the player right.",
            )
            stored_old = rulebook.add_generalized_rule(broad_old)
            natural = NaturalRuleLibrary(base / "natural_rules.json")
            old_natural = natural.merge(
                [NaturalRuleHypothesis(broad_old.summary, (old_transition.id,))]
            )[0]
            natural.mark_compiled(old_natural, stored_old)

            contradiction_before = state([2, 3, 0])
            contradiction_after = state([0, 2, 3])
            memory.append_state(contradiction_before)
            contradiction = memory.append_action_result(
                GameAction.ACTION4, contradiction_after
            )
            predictions = rulebook.predict(contradiction_before, GameAction.ACTION4)
            contradicted_ids = rulebook.record_prediction_result(
                contradiction_before,
                GameAction.ACTION4,
                contradiction_after,
                predictions,
                prediction_rule_ids=[stored_old.id],
                contradiction_id=contradiction.id,
            )

            attempts = RuleAttemptLog(base / "rule_attempt.jsonl")
            learner = RuleLearner(
                None,
                natural,
                None,
                rulebook,
                RuleVerifier(memory),
                RuleFailureLog(base / "rule_failures.jsonl"),
                attempts,
                rule_reviser=StaticReviser(
                    [move_rule(old_transition.id), push_rule(contradiction.id)]
                ),
            )

            result = learner.revise_from_memory(contradicted_ids, memory)

            self.assertEqual(result, "revision_complete")
            old_logical = rulebook.rules_by_id([stored_old.id])[0]
            self.assertEqual(old_logical.lifecycle, "superseded")
            self.assertFalse(old_logical.is_active)
            self.assertEqual(len(rulebook.active_rules()), 2)
            self.assertEqual(
                rulebook.predict(contradiction_before, GameAction.ACTION4),
                [contradiction_after],
            )
            old_natural = natural.all()[0]
            self.assertEqual(old_natural.lifecycle, "superseded")
            self.assertEqual(len([rule for rule in natural.all() if rule.lifecycle == "active"]), 2)
            self.assertTrue(old_natural.superseded_by)
            self.assertEqual(attempts.all()[0]["stage"], "revision")
            self.assertEqual(attempts.all()[0]["outcome"], "accepted")

            reloaded_rulebook = Rulebook(base)
            reloaded_natural = NaturalRuleLibrary(base / "natural_rules.json")
            self.assertEqual(reloaded_rulebook.rules_by_id([stored_old.id])[0].lifecycle, "superseded")
            self.assertEqual(reloaded_natural.all()[0].lifecycle, "superseded")

    def test_failed_revision_leaves_contradicted_rule_inactive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            memory.append_initial_state(state([2, 0]))
            old_transition = memory.append_action_result(
                GameAction.ACTION4, state([0, 2])
            )
            memory.append_state(state([2, 3, 0]))
            contradiction = memory.append_action_result(
                GameAction.ACTION4, state([0, 2, 3])
            )
            rulebook = Rulebook(base)
            old = rulebook.add_generalized_rule(
                GeneralizedRule(
                    id="",
                    action="ACTION4",
                    anchor=2,
                    conditions=(CellCondition(0, 0, 2),),
                    effects=(CellEffect(0, 0, 0), CellEffect(1, 0, 2)),
                    evidence_ids=(old_transition.id,),
                    summary="ACTION4 always moves right.",
                )
            )
            predictions = rulebook.predict(state([2, 3, 0]), GameAction.ACTION4)
            contradicted_ids = rulebook.record_prediction_result(
                state([2, 3, 0]),
                GameAction.ACTION4,
                state([0, 2, 3]),
                predictions,
                contradiction_id=contradiction.id,
            )
            natural = NaturalRuleLibrary(base / "natural_rules.json")
            hypothesis = natural.merge(
                [NaturalRuleHypothesis(old.summary, (old_transition.id,))]
            )[0]
            natural.mark_compiled(hypothesis, old)
            learner = RuleLearner(
                None,
                natural,
                None,
                rulebook,
                RuleVerifier(memory),
                RuleFailureLog(base / "rule_failures.jsonl"),
                RuleAttemptLog(base / "rule_attempt.jsonl"),
                rule_reviser=StaticReviser([move_rule(old_transition.id)]),
                max_logic_attempts=1,
            )

            result = learner.revise_from_memory(contradicted_ids, memory)

            self.assertEqual(result, "revision_failed")
            self.assertEqual(rulebook.rules_by_id([old.id])[0].lifecycle, "contradicted")
            self.assertEqual(rulebook.active_rules(), [])
            self.assertEqual(natural.all()[0].lifecycle, "contradicted")


if __name__ == "__main__":
    unittest.main()
