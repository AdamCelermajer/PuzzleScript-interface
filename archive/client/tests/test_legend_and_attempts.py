import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from client.arc.types import (
    ActionInput,
    FrameData,
    GameAction,
    GameState,
    RenderedFrame,
)
from client.engine.goal_manager import GoalManager
from client.engine.induction import LogicCompilationResult, LogicRuleCompiler, RuleLearner
from client.engine.legend import LegendInferer, LegendStore
from client.engine.memory import EngineMemory
from client.engine.natural_rules import NaturalRule, NaturalRuleLibrary, RuleFailureLog
from client.engine.perception import Perception
from client.engine.rule_attempts import RuleAttemptLog
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
from client.engine.rulebook import Rulebook
from client.engine.verifier import RuleVerifier


def frame(legend=None):
    return FrameData(
        frame=[[[2, 0], [3, 1]]],
        state=GameState.PLAYING,
        levels_completed=0,
        game_id="demo",
        win_levels=1,
        guid="guid",
        full_reset=True,
        available_actions=[GameAction.ACTION4],
        action_input=ActionInput(action=GameAction.RESET),
        legend=legend or {},
        rendered_frame=RenderedFrame(
            mime_type="image/png",
            data_url="data:image/png;base64,first-frame",
        ),
    )


class FakeLlm:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def call_json(self, system, prompt, image_data_urls=None, purpose=""):
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "images": list(image_data_urls or []),
                "purpose": purpose,
            }
        )
        return self.payload


class StaticCompiler:
    def __init__(self, candidate):
        self.candidate = candidate
        self.llm_client = SimpleNamespace(
            cfg=SimpleNamespace(model="test/model")
        )

    def compile_one(self, *_args, **_kwargs):
        return LogicCompilationResult(
            logical_rule=self.candidate,
            raw_response='{"rules":[{"summary":"raw response preserved"}]}',
            parsed_response={"rules": [{"summary": "raw response preserved"}]},
            system_prompt="compiler system",
            user_prompt="compiler prompt",
        )


class LegendAndAttemptTests(unittest.TestCase):
    def test_supplied_legend_is_normalized_and_persisted_without_llm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            llm = FakeLlm({"legend": {"0": "should not be used"}})
            store = LegendStore(Path(tmpdir) / "legend.json")
            perception = Perception(LegendInferer(llm), store, provide_legend=True)

            _state, legend = perception.initial_perception(
                frame({0: "Background", 2: "Player", 3: "Crate", 1: "Wall"})
            )

            self.assertEqual(legend[2], "Player")
            self.assertEqual(llm.calls, [])
            self.assertEqual(LegendStore(store.path).all(), legend)

    def test_disabled_supplied_legend_infers_from_first_grid_and_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            llm = FakeLlm(
                {"legend": {"0": "Floor", "1": "Wall", "2": "Player", "3": "Crate"}}
            )
            store = LegendStore(Path(tmpdir) / "legend.json")
            perception = Perception(LegendInferer(llm), store, provide_legend=False)

            _state, legend = perception.initial_perception(frame({2: "Ignored"}))

            self.assertEqual(legend[3], "Crate")
            self.assertEqual(llm.calls[0]["purpose"], "legend inference")
            self.assertEqual(
                llm.calls[0]["images"], ["data:image/png;base64,first-frame"]
            )
            self.assertNotIn("Background", llm.calls[0]["prompt"])

    def test_goal_can_be_inferred_before_action_with_legend_context(self):
        llm = FakeLlm({"goal": "place every crate on a target"})
        state = Perception().perceive(frame())
        goal = GoalManager(llm, provide_end_goal=False).define_task_goal(
            state, {2: "Player", 3: "Crate"}
        )

        self.assertEqual(goal.description, "place every crate on a target")
        self.assertEqual(llm.calls[0]["purpose"], "task goal")
        self.assertIn("3 = Crate", llm.calls[0]["prompt"])

    def test_rule_attempt_log_keeps_raw_response_and_cell_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            perception = Perception()
            before = perception.perceive(frame())
            after_frame = frame()
            after_frame.frame = [[[0, 2], [3, 1]]]
            after_frame.action_input = ActionInput(action=GameAction.ACTION4)
            after = perception.perceive(after_frame)
            memory.append_initial_state(before)
            transition = memory.append_action_result(GameAction.ACTION4, after)
            candidate = GeneralizedRule(
                id="candidate",
                action="ACTION4",
                anchor=2,
                conditions=(CellCondition(dx=0, dy=0, value=2),),
                effects=(CellEffect(dx=0, dy=0, value=2),),
                evidence_ids=(transition.id,),
                summary="Incorrectly predicts no movement.",
            )
            attempts = RuleAttemptLog(base / "rule_attempt.jsonl")
            learner = RuleLearner(
                None,
                NaturalRuleLibrary(base / "natural_rules.json"),
                StaticCompiler(candidate),
                Rulebook(base),
                RuleVerifier(memory),
                RuleFailureLog(base / "rule_failures.jsonl"),
                attempts,
                max_logic_attempts=1,
            )
            hypothesis = NaturalRule(
                id="N000001",
                summary="ACTION4 moves the player right.",
                evidence_ids=(transition.id,),
            )

            result, _failure = learner.compile_and_verify(
                hypothesis, transition, [], memory
            )
            record = attempts.all()[0]

            self.assertIsNone(result)
            self.assertIn("raw response preserved", record["raw_response"])
            self.assertEqual(record["candidate"]["ruleID"], "candidate")
            diagnostic = record["verification"]["diagnostics"][0]
            self.assertEqual(diagnostic["type"], "prediction_mismatch")
            self.assertTrue(diagnostic["closest_cell_differences"])

    def test_logic_compiler_defines_offsets_as_dx_dy(self):
        llm = FakeLlm({"rules": []})
        compiler = LogicRuleCompiler(llm)
        transition = SimpleNamespace(
            to_data=lambda: {},
        )
        hypothesis = NaturalRule(
            id="N000001",
            summary="ACTION1 moves the player up.",
            evidence_ids=("T000001",),
        )

        compiler.compile_one(transition, hypothesis, [], [], [], legend={2: "Player"})

        system = llm.calls[0]["system"]
        self.assertIn("Offsets are [dx, dy]", system)
        self.assertIn("up is [0, -1]", system)
        self.assertIn("first number never represents a row", system)


if __name__ == "__main__":
    unittest.main()
