import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from client.arc.types import ActionInput, FrameData, GameAction, GameState
from client.engine.action_selector import ActionSelector, ProbePlanner
from client.engine.goal_manager import Goal, GoalManager
from client.engine.induction import (
    LogicCompilationResult,
    NaturalInductionResult,
    NaturalRuleHypothesis,
    RuleLearner,
    natural_rule_hypotheses_from_llm_json,
)
from client.engine.memory import EngineMemory
from client.engine.natural_rules import NaturalRuleLibrary, RuleFailureLog
from client.engine.perception import Perception
from client.engine.planner import RulePlanner
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
from client.engine.rulebook import Rulebook
from client.engine.verifier import RuleVerifier


def frame(grid, state=GameState.PLAYING, action=GameAction.RESET):
    return FrameData(
        frame=[grid],
        state=state,
        levels_completed=1 if state == GameState.WIN else 0,
        game_id="test-game",
        win_levels=1,
        guid="guid",
        full_reset=action == GameAction.RESET,
        available_actions=[GameAction.ACTION4],
        action_input=ActionInput(action=action),
    )


class StaticNaturalInducer:
    def infer(self, transition, events, images, previous_rules, game_name):
        return NaturalInductionResult(
            hypotheses=(
                NaturalRuleHypothesis(
                    "ACTION4 moves the actor right.", (transition.id,)
                ),
            )
        )


class AlwaysFailCompiler:
    def __init__(self):
        self.failures = []

    def compile_one(
        self,
        transition,
        hypothesis,
        all_natural_rules,
        logical_rules,
        images,
        previous_failure="",
    ):
        self.failures.append(previous_failure)
        return LogicCompilationResult(failure_reason=f"bad candidate {len(self.failures)}")


class SuccessfulCompiler:
    def compile_one(
        self,
        transition,
        hypothesis,
        all_natural_rules,
        logical_rules,
        images,
        previous_failure="",
    ):
        return LogicCompilationResult(
            logical_rule=GeneralizedRule(
                id="",
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
                summary=hypothesis.summary,
            )
        )


class PseudocodeAgentTests(unittest.TestCase):
    def test_natural_rule_response_rejects_multiple_candidates(self):
        with self.assertRaisesRegex(ValueError, "at most one rule"):
            natural_rule_hypotheses_from_llm_json(
                {
                    "rules": [
                        {"summary": "first", "evidence_ids": ["T000001"]},
                        {"summary": "second", "evidence_ids": ["T000001"]},
                    ]
                }
            )

    def test_task_goal_uses_terminal_state(self):
        perception = Perception()
        goal = GoalManager().define_task_goal(perception.perceive(frame([[2, 0]])))
        self.assertFalse(goal.reached_by(perception.perceive(frame([[2, 0]]))))
        self.assertTrue(
            goal.reached_by(
                perception.perceive(frame([[0, 2]], state=GameState.WIN))
            )
        )

    def test_action_selector_continues_probe_plan_and_attaches_predictions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            state = Perception().perceive(frame([[2, 0]]))
            memory.append_initial_state(state)
            rulebook = Rulebook(Path(tmpdir))
            goal_manager = SimpleNamespace(
                choose_subgoal=lambda **_kwargs: Goal("probe twice", kind="subgoal")
            )
            probe_planner = SimpleNamespace(
                create_plan=lambda **_kwargs: [GameAction.ACTION4, GameAction.ACTION4]
            )
            selector = ActionSelector(
                RulePlanner(rulebook),
                goal_manager,
                probe_planner,
                rulebook,
                memory,
            )

            first = selector.choose_action(
                state, Goal("complete", kind="game_goal"), [GameAction.ACTION4]
            )
            second = selector.choose_action(
                state, Goal("complete", kind="game_goal"), [GameAction.ACTION4]
            )

            self.assertEqual(first.source, "explore_subgoal")
            self.assertEqual(second.source, "active_plan")
            self.assertEqual(first.predictions, ())
            self.assertEqual(first.remaining_actions, (GameAction.ACTION4,))
            self.assertEqual(second.plan, [GameAction.ACTION4])
            self.assertEqual(second.remaining_actions, ())

    def test_action_selector_falls_back_after_malformed_action_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            state = Perception().perceive(frame([[2, 0]]))
            memory.append_initial_state(state)
            rulebook = Rulebook(Path(tmpdir))
            events = []
            selector = ActionSelector(
                RulePlanner(rulebook),
                SimpleNamespace(
                    choose_subgoal=lambda **_kwargs: Goal("probe", kind="subgoal")
                ),
                SimpleNamespace(
                    create_plan=lambda **_kwargs: (_ for _ in ()).throw(
                        ValueError("LLM returned invalid JSON")
                    )
                ),
                rulebook,
                memory,
                event_sink=events.append,
            )

            decision = selector.choose_action(
                state, Goal("complete", kind="game_goal"), [GameAction.ACTION4]
            )

            self.assertEqual(decision.action, GameAction.ACTION4)
            self.assertEqual(decision.plan, [GameAction.ACTION4])
            self.assertIn("one-action fallback", events[0])

    def test_natural_rule_library_persists_separately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "natural_rules.json"
            library = NaturalRuleLibrary(path)
            created = library.merge(
                [NaturalRuleHypothesis("A visible rule.", ("T000001",))]
            )
            library.mark_compiled(created[0], SimpleNamespace(id="G000001"))

            loaded = NaturalRuleLibrary(path)

            self.assertEqual(loaded.all()[0].status, "compiled")
            self.assertEqual(loaded.all()[0].logical_rule_id, "G000001")

    def test_rule_learner_retries_logs_without_persisting_rejected_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            perception = Perception()
            memory.append_initial_state(perception.perceive(frame([[2, 0]])))
            memory.append_action_result(
                GameAction.ACTION4,
                perception.perceive(frame([[0, 2]], action=GameAction.ACTION4)),
            )
            library = NaturalRuleLibrary(base / "natural_rules.json")
            failure_log = RuleFailureLog(base / "rule_failures.jsonl")
            compiler = AlwaysFailCompiler()
            learner = RuleLearner(
                StaticNaturalInducer(),
                library,
                compiler,
                Rulebook(base),
                RuleVerifier(memory),
                failure_log,
                max_logic_attempts=3,
            )

            result = learner.learn_from_memory("test-game", memory)

            self.assertEqual(result, "learning_complete")
            self.assertEqual(len(compiler.failures), 3)
            self.assertEqual(compiler.failures, ["", "bad candidate 1", "bad candidate 2"])
            self.assertEqual(library.all(), [])
            self.assertEqual(len(failure_log.recent()), 3)

    def test_verified_equivalent_rules_reuse_one_natural_rule(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            library = NaturalRuleLibrary(base / "natural_rules.json")
            logical = GeneralizedRule(
                id="G000001",
                action="ACTION4",
                anchor=2,
                conditions=(CellCondition(dx=0, dy=0, value=2),),
                effects=(CellEffect(dx=1, dy=0, value=2),),
                evidence_ids=("T000001",),
                summary="ACTION4 moves the actor right.",
            )
            first, created = library.promote(
                NaturalRuleHypothesis(
                    "The actor moved right.", ("T000001",), "ACTION4"
                ),
                logical,
            )
            second, reused = library.promote(
                NaturalRuleHypothesis(
                    "The piece advanced right.", ("T000002",), "ACTION4"
                ),
                logical,
            )

            self.assertTrue(created)
            self.assertFalse(reused)
            self.assertEqual(first.id, second.id)
            self.assertEqual(second.summary, "ACTION4 moves the actor right.")
            self.assertEqual(second.evidence_ids, ("T000001", "T000002"))

    def test_fourth_exhausted_hypothesis_stops_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            perception = Perception()
            memory.append_initial_state(perception.perceive(frame([[2, 0]])))
            memory.append_action_result(
                GameAction.ACTION4,
                perception.perceive(frame([[0, 2]], action=GameAction.ACTION4)),
            )
            counter = {"value": 0}

            class UniqueInducer:
                def infer(self, transition, events, images, previous_rules, game_name):
                    counter["value"] += 1
                    return NaturalInductionResult(
                        hypotheses=(
                            NaturalRuleHypothesis(
                                f"Hypothesis {counter['value']}", (transition.id,)
                            ),
                        )
                    )

            learner = RuleLearner(
                UniqueInducer(),
                NaturalRuleLibrary(base / "natural_rules.json"),
                AlwaysFailCompiler(),
                Rulebook(base),
                RuleVerifier(memory),
                RuleFailureLog(base / "rule_failures.jsonl"),
                max_logic_attempts=1,
                allowed_exhausted_hypotheses=3,
            )

            results = [learner.learn_from_memory("test-game", memory) for _ in range(4)]

            self.assertEqual(results[-1], "stop_required")
            self.assertEqual(learner.exhausted_hypothesis_count, 4)

    def test_verified_rule_resets_consecutive_exhausted_hypotheses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            perception = Perception()
            memory.append_initial_state(perception.perceive(frame([[2, 0]])))
            memory.append_action_result(
                GameAction.ACTION4,
                perception.perceive(frame([[0, 2]], action=GameAction.ACTION4)),
            )
            learner = RuleLearner(
                StaticNaturalInducer(),
                NaturalRuleLibrary(base / "natural_rules.json"),
                SuccessfulCompiler(),
                Rulebook(base),
                RuleVerifier(memory),
                RuleFailureLog(base / "rule_failures.jsonl"),
            )
            learner.exhausted_hypothesis_count = 3

            result = learner.learn_from_memory("test-game", memory)

            self.assertEqual(result, "learning_complete")
            self.assertEqual(learner.exhausted_hypothesis_count, 0)


if __name__ == "__main__":
    unittest.main()
