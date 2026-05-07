import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from client.engine.agent import Agent, run_solving_loop
from client.engine.history import TransitionHistory
from client.engine.llm_client import Config
from client.engine.perceiver import Perceiver
from client.engine.rules import RuleLibrary
from client.engine.types import ActionInput, FrameData, GameAction, GameState


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
        game_id="line-world",
        win_levels=1,
        guid="line-world",
        full_reset=(action == GameAction.RESET),
        available_actions=available_actions
        if available_actions is not None
        else [GameAction.ACTION3, GameAction.ACTION4, GameAction.RESET],
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
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, str, str, bool]] = []
        self.event_sink = None

    def _call(
        self,
        system: str,
        prompt: str,
        model_type: str = "flash",
        json_mode: bool = False,
    ) -> str:
        self.calls.append((system, prompt, model_type, json_mode))
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        return self.responses.pop(0)


class EngineArchitectureTests(unittest.TestCase):
    def _config(self, rules_dir: str, *, max_steps: int = 3) -> Config:
        return Config(
            openrouter_api_key="test-openrouter-key",
            game="line-world",
            max_steps=max_steps,
            mode="solve",
            rules_dir=rules_dir,
        )

    def test_transition_history_persists_state_action_state_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perceiver = Perceiver()
            history = TransitionHistory(Path(tmpdir) / "transitions.jsonl")
            before = perceiver.perceive(_frame([[2, 0]]))
            after = perceiver.perceive(_frame([[0, 2]], action=GameAction.ACTION4))

            record = history.add(before, GameAction.ACTION4, after)

            self.assertEqual(record.id, "T000001")
            self.assertEqual(history.recent(1), [record])
            text = (Path(tmpdir) / "transitions.jsonl").read_text(encoding="utf-8")
            self.assertIn('"action": "ACTION4"', text)
            self.assertIn('"before"', text)
            self.assertIn('"after"', text)

    def test_rule_library_verifies_hits_and_rejects_failed_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perceiver = Perceiver()
            history = TransitionHistory(Path(tmpdir) / "transitions.jsonl")
            library = RuleLibrary(Path(tmpdir))
            before = perceiver.perceive(_frame([[2, 0]]))
            after = perceiver.perceive(_frame([[0, 2]], action=GameAction.ACTION4))
            unexpected = perceiver.perceive(_frame([[2, 0]], action=GameAction.ACTION4))

            first = history.add(before, GameAction.ACTION4, after)
            library.add_hypotheses(["moving right shifts the active object"], first)
            library.record_transition(first)

            self.assertNotIn("exact observed transition", library.known_rules_text())
            markdown = (Path(tmpdir) / "rules.md").read_text(encoding="utf-8")
            self.assertIn("## Executable State Transitions", markdown)
            self.assertIn("## LLM Rule Hypotheses", markdown)

            predictions = library.predict(before, GameAction.ACTION4)
            library.record_prediction_result(
                before, GameAction.ACTION4, after, predictions
            )

            hypothesis = library.hypotheses()[0]
            self.assertEqual(hypothesis.status, "verified")
            self.assertEqual(hypothesis.prediction_hits, 1)

            predictions = library.predict(before, GameAction.ACTION4)
            library.record_prediction_result(
                before, GameAction.ACTION4, unexpected, predictions
            )

            transition_rule = next(
                rule for rule in library.rules if rule.kind == "transition"
            )
            self.assertEqual(transition_rule.status, "rejected")
            self.assertEqual(transition_rule.prediction_failures, 1)

    def test_solving_loop_uses_verified_plan_instead_of_placeholder_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._config(tmpdir, max_steps=2)
            agent = Agent(cfg, FakeLlmClient())
            start = Perceiver().perceive(_frame([[2, 0, 0]]))
            middle = Perceiver().perceive(_frame([[0, 2, 0]], action=GameAction.ACTION4))
            win = Perceiver().perceive(
                _frame([[0, 0, 2]], state=GameState.WIN, action=GameAction.ACTION4)
            )
            first = agent.engine.history.add(start, GameAction.ACTION4, middle)
            second = agent.engine.history.add(middle, GameAction.ACTION4, win)
            agent.engine.library.record_transition(first)
            agent.engine.library.record_transition(second)

            env = FakeEnv(
                reset_frame=_frame([[2, 0, 0]]),
                step_frames=[
                    _frame([[0, 2, 0]], action=GameAction.ACTION4),
                    _frame([[0, 0, 2]], state=GameState.WIN, action=GameAction.ACTION4),
                ],
            )

            with patch("client.engine.agent.time.sleep", return_value=None):
                run_solving_loop(cfg, env, agent)

            self.assertEqual(env.step_actions, [GameAction.ACTION4, GameAction.ACTION4])

    def test_solving_loop_asks_llm_for_subgoal_when_no_verified_plan_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._config(tmpdir, max_steps=2)
            llm = FakeLlmClient(
                [
                    '{"subgoal": "move right to test empty space", '
                    '"plan": ["ACTION4"]}',
                    '{"subgoal": "move left to compare the reverse", '
                    '"plan": ["ACTION3"]}',
                ]
            )
            agent = Agent(cfg, llm)
            env = FakeEnv(
                reset_frame=_frame([[2, 0]]),
                step_frames=[
                    _frame([[0, 2]], action=GameAction.ACTION4),
                    _frame([[2, 0]], action=GameAction.ACTION3),
                ],
            )

            with patch("client.engine.agent.time.sleep", return_value=None):
                run_solving_loop(cfg, env, agent)

            self.assertEqual(env.step_actions, [GameAction.ACTION4, GameAction.ACTION3])
            self.assertEqual(len(llm.calls), 2)
            self.assertIn("Available actions: ACTION3, ACTION4", llm.calls[0][1])
            self.assertNotIn("expected_observation", llm.calls[0][0] + llm.calls[0][1])

    def test_llm_can_choose_action7_when_backend_exposes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._config(tmpdir, max_steps=1)
            llm = FakeLlmClient(
                ['{"subgoal": "test undo behavior", "plan": ["ACTION7"]}']
            )
            agent = Agent(cfg, llm)
            env = FakeEnv(
                reset_frame=_frame(
                    [[2, 0]],
                    available_actions=[
                        GameAction.ACTION7,
                        GameAction.ACTION4,
                        GameAction.RESET,
                    ],
                ),
                step_frames=[
                    _frame(
                        [[2, 0]],
                        action=GameAction.ACTION7,
                        available_actions=[
                            GameAction.ACTION7,
                            GameAction.ACTION4,
                            GameAction.RESET,
                        ],
                    )
                ],
            )

            with patch("client.engine.agent.time.sleep", return_value=None):
                run_solving_loop(cfg, env, agent)

            self.assertEqual(env.step_actions, [GameAction.ACTION7])
            self.assertEqual(len(llm.calls), 1)
            self.assertIn("Available actions: ACTION4, ACTION7", llm.calls[0][1])


if __name__ == "__main__":
    unittest.main()
