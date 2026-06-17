import tempfile
import json
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from client.engine.agent import Agent, run_solving_loop
from client.engine.llm_client import Config
from client.engine.memory import EngineMemory
from client.engine.perception import Perception
from client.engine.rulebook import Rulebook
from client.arc.types import (
    ActionInput,
    FrameData,
    GameAction,
    GameState,
    RenderedFrame,
)


def _frame(
    grid: list[list[int]],
    *,
    state: GameState = GameState.PLAYING,
    action: GameAction = GameAction.RESET,
    available_actions: list[GameAction] | None = None,
    rendered_frame: RenderedFrame | None = None,
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
        rendered_frame=rendered_frame,
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


class FakeImageLlmClient:
    def __init__(self, response: dict) -> None:
        self.response = response
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
        return self.response


class EngineArchitectureTests(unittest.TestCase):
    def _config(self, rules_dir: str, *, max_steps: int = 3) -> Config:
        return Config(
            openrouter_api_key="test-openrouter-key",
            game="line-world",
            max_steps=max_steps,
            mode="solve",
            rules_dir=rules_dir,
        )

    def test_memory_persists_state_action_state_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            before = perception.perceive(_frame([[2, 0]]))
            after = perception.perceive(_frame([[0, 2]], action=GameAction.ACTION4))

            memory.append_initial_state(before)
            record = memory.append_action_result(GameAction.ACTION4, after)

            self.assertEqual(record.id, "T000001")
            self.assertEqual([item.kind for item in memory.timeline], ["state", "action", "state"])
            self.assertEqual(memory.recent(1), [record])
            text = (Path(tmpdir) / "timeline.jsonl").read_text(encoding="utf-8")
            self.assertIn('"kind": "state"', text)
            self.assertIn('"kind": "action"', text)
            self.assertIn('"before_id": "S000001"', text)
            self.assertIn('"after_id": "S000002"', text)

    def test_rulebook_verifies_hits_and_rejects_failed_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            rulebook = Rulebook(Path(tmpdir))
            before = perception.perceive(_frame([[2, 0]]))
            after = perception.perceive(_frame([[0, 2]], action=GameAction.ACTION4))
            unexpected = perception.perceive(_frame([[2, 0]], action=GameAction.ACTION4))

            first = memory.record_transition(before, GameAction.ACTION4, after)
            rulebook.add_hypotheses(["moving right shifts the active object"], first)
            rulebook.record_transition(first)

            self.assertNotIn("exact observed transition", rulebook.known_rules_text())
            markdown = (Path(tmpdir) / "rules.md").read_text(encoding="utf-8")
            self.assertIn("## Executable State Transitions", markdown)
            self.assertIn("## LLM Rule Hypotheses", markdown)

            predictions = rulebook.predict(before, GameAction.ACTION4)
            rulebook.record_prediction_result(before, GameAction.ACTION4, after, predictions)

            hypothesis = rulebook.hypotheses()[0]
            self.assertEqual(hypothesis.status, "verified")
            self.assertEqual(hypothesis.prediction_hits, 1)

            predictions = rulebook.predict(before, GameAction.ACTION4)
            rulebook.record_prediction_result(
                before, GameAction.ACTION4, unexpected, predictions
            )

            transition_rule = next(
                rule for rule in rulebook.rules if rule.kind == "transition"
            )
            self.assertEqual(transition_rule.status, "rejected")
            self.assertEqual(transition_rule.prediction_failures, 1)

    def test_solving_loop_uses_verified_plan_instead_of_placeholder_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._config(tmpdir, max_steps=2)
            agent = Agent(cfg, FakeLlmClient())
            start = Perception().perceive(_frame([[2, 0, 0]]))
            middle = Perception().perceive(_frame([[0, 2, 0]], action=GameAction.ACTION4))
            win = Perception().perceive(
                _frame([[0, 0, 2]], state=GameState.WIN, action=GameAction.ACTION4)
            )
            first = agent.engine.memory.record_transition(
                start, GameAction.ACTION4, middle
            )
            second = agent.engine.memory.record_transition(
                middle, GameAction.ACTION4, win
            )
            agent.engine.rulebook.record_transition(first)
            agent.engine.rulebook.record_transition(second)

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
                    '{"subgoal": "move right to test empty space", "plan": ["ACTION4"]}',
                    '{"rules": []}',
                    '{"subgoal": "move left to compare the reverse", "plan": ["ACTION3"]}',
                    '{"rules": []}',
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
            self.assertEqual(len(llm.calls), 4)
            self.assertIn("Available actions: ACTION3, ACTION4", llm.calls[0][1])
            self.assertNotIn("expected_observation", llm.calls[0][0] + llm.calls[0][1])

    def test_llm_can_choose_action7_when_backend_exposes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._config(tmpdir, max_steps=1)
            llm = FakeLlmClient(
                [
                    '{"subgoal": "test undo behavior", "plan": ["ACTION7"]}',
                    '{"rules": []}',
                ]
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
            self.assertEqual(len(llm.calls), 2)
            self.assertIn("Available actions: ACTION4, ACTION7", llm.calls[0][1])

    def test_planner_attaches_state_image_to_llm_subgoal_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_url = "data:image/png;base64,iVBORw0KGgo="
            llm = FakeImageLlmClient(
                {"subgoal": "inspect rendered board", "plan": ["ACTION4"]}
            )
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            rulebook = Rulebook(Path(tmpdir))
            from client.engine.planner import Planner

            frame = _frame(
                [[2, 0]],
                rendered_frame=RenderedFrame(
                    mime_type="image/png",
                    data_url=image_url,
                    width=10,
                    height=10,
                ),
            )
            memory.append_initial_state(Perception().perceive(frame))
            planner = Planner(rulebook=rulebook, memory=memory, llm_client=llm)

            decision = planner.choose_action()

            self.assertEqual(decision.action, GameAction.ACTION4)
            self.assertEqual(llm.calls[0]["image_data_urls"], [image_url])
            self.assertIn("Rendered image context is attached.", llm.calls[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
