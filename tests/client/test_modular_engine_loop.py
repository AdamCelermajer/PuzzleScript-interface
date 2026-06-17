import tempfile
import json
import unittest
from dataclasses import dataclass, field
from pathlib import Path
import os
import sys
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from client.engine.memory import EngineMemory
from client.engine.perception import Perception
from client.engine.planner import PlanDecision
from client.engine.rulebook import Rulebook
from client.arc.types import ActionInput, FrameData, GameAction, GameState


def _frame(
    grid: list[list[int]],
    *,
    state: GameState = GameState.PLAYING,
    action: GameAction = GameAction.RESET,
    available_actions: list[GameAction] | None = None,
) -> FrameData:
    return FrameData(
        frame=[grid],
        state=state,
        levels_completed=1 if state == GameState.WIN else 0,
        game_id="modular-world",
        win_levels=1,
        guid="modular-world",
        full_reset=(action == GameAction.RESET),
        available_actions=available_actions
        if available_actions is not None
        else [GameAction.ACTION4, GameAction.RESET],
        action_input=ActionInput(action=action),
        legend={},
    )


@dataclass
class FakeEnv:
    reset_frame: FrameData
    step_frames: list[FrameData]
    session_id: str = "fake-session"
    step_actions: list[GameAction] = field(default_factory=list)

    def reset(self) -> FrameData:
        return self.reset_frame

    def step(self, action: GameAction) -> FrameData:
        self.step_actions.append(action)
        index = min(len(self.step_actions) - 1, len(self.step_frames) - 1)
        return self.step_frames[index]


class FakeLlmClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, str, bool]] = []

    def _call(
        self,
        system: str,
        prompt: str,
        json_mode: bool = False,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> str:
        self.calls.append((system, prompt, json_mode, purpose))
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        return self.responses.pop(0)

    def call_json(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> dict:
        return json.loads(
            self._call(
                system,
                prompt,
                json_mode=True,
                image_data_urls=image_data_urls,
                purpose=purpose,
            )
        )


class ModularEngineLoopTests(unittest.TestCase):
    def test_action_executor_returns_before_after_outcome(self) -> None:
        from client.runtime.runner import ActionExecutor

        before_frame = _frame([[2, 0], [0, 0]])
        after_frame = _frame([[0, 2], [0, 0]], action=GameAction.ACTION4)
        before_state = Perception().perceive(before_frame)
        env = FakeEnv(before_frame, [after_frame])
        decision = PlanDecision(GameAction.ACTION4, "test", [GameAction.ACTION4])

        outcome = ActionExecutor(env, Perception()).execute(
            before_frame, before_state, decision
        )

        self.assertIs(outcome.before_frame, before_frame)
        self.assertEqual(outcome.before_state, before_state)
        self.assertEqual(outcome.action, GameAction.ACTION4)
        self.assertIs(outcome.after_frame, after_frame)
        self.assertEqual(outcome.after_state.grid, ((0, 2), (0, 0)))

    def test_memory_and_rulebook_record_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            before = perception.perceive(_frame([[2, 0]]))
            after = perception.perceive(_frame([[0, 2]], action=GameAction.ACTION4))
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            rulebook = Rulebook(Path(tmpdir))

            record = memory.record_transition(before, GameAction.ACTION4, after)
            rulebook.record_prediction_result(before, GameAction.ACTION4, after, [])
            rule = rulebook.record_transition(record)

            self.assertEqual(record.id, "T000001")
            self.assertEqual(memory.recent(1), [record])
            self.assertEqual(rule.status, "verified")
            self.assertTrue(rulebook.predict(before, GameAction.ACTION4))

    def test_named_architecture_modules_are_importable(self) -> None:
        from client.engine.goal_manager import GoalManager
        from client.engine.perception import EngineState, Perception
        from client.engine.planner import Planner

        self.assertIsNotNone(GoalManager)
        self.assertIsNotNone(EngineState)
        self.assertIsNotNone(Perception)
        self.assertIsNotNone(Planner)

    def test_rule_reasoning_loop_records_one_learning_step(self) -> None:
        from client.runtime.runner import ActionExecutor, RuleReasoningLoop
        from client.engine.induction import RuleInducer
        from client.engine.planner import Planner
        from client.engine.verifier import RuleVerifier

        with tempfile.TemporaryDirectory() as tmpdir:
            before_frame = _frame([[2, 0]])
            after_frame = _frame([[0, 2]], action=GameAction.ACTION4)
            env = FakeEnv(before_frame, [after_frame])
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeLlmClient(
                [
                    '{"subgoal": "move right to test empty space", "plan": ["ACTION4"]}',
                    '{"rules": []}',
                ]
            )
            planner = Planner(rulebook=rulebook, memory=memory, llm_client=llm)
            inducer = RuleInducer(llm, rulebook, RuleVerifier(memory))
            loop = RuleReasoningLoop(
                env,
                Perception(),
                memory,
                rulebook,
                planner,
                inducer,
                ActionExecutor(env, Perception()),
                sleep_fn=lambda _seconds: None,
            )

            loop.run_learning(max_steps=1, game_id="modular-world")

            self.assertEqual(env.step_actions, [GameAction.ACTION4])
            self.assertEqual(memory.recent(1)[0].action, GameAction.ACTION4)
            self.assertTrue(rulebook.predict(memory.recent(1)[0].before, GameAction.ACTION4))

    def test_unified_loop_induces_rules_after_each_unexplained_llm_action(
        self,
    ) -> None:
        from client.runtime.runner import ActionExecutor, RuleReasoningLoop
        from client.engine.induction import RuleInducer
        from client.engine.planner import Planner
        from client.engine.verifier import RuleVerifier

        with tempfile.TemporaryDirectory() as tmpdir:
            before_frame = _frame([[2, 0, 0]])
            middle_frame = _frame([[0, 2, 0]], action=GameAction.ACTION4)
            after_frame = _frame([[0, 0, 2]], action=GameAction.ACTION4)
            env = FakeEnv(before_frame, [middle_frame, after_frame])
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeLlmClient(
                [
                    '{"subgoal": "try moving right twice", "plan": ["ACTION4", "ACTION4"]}',
                    '{"rules": []}',
                    '{"subgoal": "re-plan after the observed move", "plan": ["ACTION4"]}',
                    '{"rules": []}',
                ]
            )
            planner = Planner(rulebook=rulebook, memory=memory, llm_client=llm)
            inducer = RuleInducer(llm, rulebook, RuleVerifier(memory))
            loop = RuleReasoningLoop(
                env,
                Perception(),
                memory,
                rulebook,
                planner,
                inducer,
                ActionExecutor(env, Perception()),
                sleep_fn=lambda _seconds: None,
            )

            loop.run(max_steps=2, game_id="modular-world")

            self.assertEqual(env.step_actions, [GameAction.ACTION4, GameAction.ACTION4])
            self.assertEqual(len(llm.calls), 4)
            self.assertIn("choose a small useful subgoal", llm.calls[0][0])
            self.assertIn("propose executable mechanical rules", llm.calls[1][0])
            self.assertIn("choose a small useful subgoal", llm.calls[2][0])
            self.assertIn("propose executable mechanical rules", llm.calls[3][0])

    def test_runtime_runner_executes_engine_decisions_outside_engine(self) -> None:
        from client.runtime.runner import ActionExecutor

        before_frame = _frame([[2, 0]])
        after_frame = _frame([[0, 2]], action=GameAction.ACTION4)
        before_state = Perception().perceive(before_frame)
        env = FakeEnv(before_frame, [after_frame])
        decision = PlanDecision(GameAction.ACTION4, "test", [GameAction.ACTION4])

        outcome = ActionExecutor(env, Perception()).execute(
            before_frame, before_state, decision
        )

        self.assertEqual(env.step_actions, [GameAction.ACTION4])
        self.assertEqual(outcome.action, GameAction.ACTION4)


if __name__ == "__main__":
    unittest.main()
