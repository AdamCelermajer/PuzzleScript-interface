import os
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from client.engine.agent import Agent, run_learning_loop, run_solving_loop
from client.engine.llm_client import Config
from client.arc.types import ActionInput, FrameData, GameAction, GameState


def _frame(
    *,
    state: GameState = GameState.PLAYING,
    action: GameAction = GameAction.RESET,
    frame: list[list[list[int]]] | None = None,
    available_actions: list[GameAction] | None = None,
) -> FrameData:
    return FrameData(
        frame=frame if frame is not None else [[[0, 0], [0, 0]]],
        state=state,
        levels_completed=0,
        game_id="ps_sokoban_basic-v1",
        win_levels=1,
        guid="guid-1",
        full_reset=(action == GameAction.RESET),
        available_actions=available_actions
        if available_actions is not None
        else [
            GameAction.ACTION1,
            GameAction.ACTION2,
            GameAction.ACTION3,
            GameAction.ACTION4,
            GameAction.ACTION5,
            GameAction.RESET,
        ],
        action_input=ActionInput(action=action),
        legend={},
    )


@dataclass
class FakeEnv:
    reset_frames: list[FrameData]
    step_frames: list[FrameData]
    session_id: str = "fake-session"
    reset_calls: int = 0
    step_actions: list[GameAction] = field(default_factory=list)

    def reset(self) -> FrameData:
        index = min(self.reset_calls, len(self.reset_frames) - 1)
        self.reset_calls += 1
        return self.reset_frames[index]

    def step(self, action: GameAction) -> FrameData:
        self.step_actions.append(action)
        index = min(len(self.step_actions) - 1, len(self.step_frames) - 1)
        return self.step_frames[index]


class FakeLlmClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
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


class AgentLoopTests(unittest.TestCase):
    def _make_config(self, *, max_steps: int = 2, mode: str = "learn") -> Config:
        tmpdir = tempfile.mkdtemp()
        return Config(
            openrouter_api_key="test-openrouter-key",
            game="ps_sokoban_basic-v1",
            max_steps=max_steps,
            mode=mode,
            rules_dir=tmpdir,
        )

    def test_learning_loop_records_engine_evidence_from_llm_subgoal_actions(self) -> None:
        cfg = self._make_config(max_steps=2, mode="learn")
        llm = FakeLlmClient(
            [
                '{"subgoal": "probe the first move", "plan": ["ACTION1"]}',
                '{"rules": []}',
                '{"subgoal": "probe the second move", "plan": ["ACTION2"]}',
                '{"rules": []}',
            ]
        )
        agent = Agent(cfg, llm)
        env = FakeEnv(
            reset_frames=[_frame(frame=[[[0, 0], [0, 0]]])],
            step_frames=[
                _frame(action=GameAction.ACTION1, frame=[[[0, 1], [0, 0]]]),
                _frame(action=GameAction.ACTION2, frame=[[[0, 1], [0, 1]]]),
            ],
        )

        with patch("client.engine.agent.time.sleep", return_value=None):
            run_learning_loop(cfg, env, agent)

        self.assertEqual(env.step_actions, [GameAction.ACTION1, GameAction.ACTION2])
        self.assertEqual(len(llm.calls), 4)
        self.assertTrue(
            os.path.exists(os.path.join(cfg.rules_dir, cfg.game, "timeline.jsonl"))
        )
        self.assertTrue(
            os.path.exists(os.path.join(cfg.rules_dir, cfg.game, "rules.json"))
        )

    def test_local_sokoban_uses_new_rule_library_store(self) -> None:
        rules_dir = tempfile.mkdtemp()
        cfg = Config(
            openrouter_api_key="test-openrouter-key",
            game="ps_sokoban_basic-v1",
            max_steps=2,
            mode="learn",
            rules_dir=rules_dir,
        )

        agent = Agent(cfg, FakeLlmClient([]))

        self.assertEqual(agent.engine.rulebook.generalized_rules, [])
        self.assertTrue(str(agent.engine.base_path).endswith("ps_sokoban_basic-v1"))

    def test_solving_loop_explores_available_actions_without_reset(self) -> None:
        cfg = self._make_config(max_steps=3, mode="solve")
        llm = FakeLlmClient(
            [
                '{"subgoal": "try the first open direction", "plan": ["ACTION1"]}',
                '{"rules": []}',
                '{"subgoal": "try the next open direction", "plan": ["ACTION3"]}',
                '{"rules": []}',
                '{"subgoal": "finish the small board", "plan": ["ACTION1"]}',
                '{"rules": []}',
            ]
        )
        agent = Agent(cfg, llm)
        events: list[str] = []
        env = FakeEnv(
            reset_frames=[
                _frame(
                    frame=[[[0, 0], [0, 0]]],
                    available_actions=[
                        GameAction.ACTION1,
                        GameAction.ACTION3,
                        GameAction.RESET,
                    ],
                )
            ],
            step_frames=[
                _frame(action=GameAction.ACTION1, frame=[[[1, 0], [0, 0]]]),
                _frame(action=GameAction.ACTION3, frame=[[[1, 1], [0, 0]]]),
                _frame(
                    state=GameState.WIN,
                    action=GameAction.ACTION1,
                    frame=[[[1, 1], [1, 0]]],
                ),
            ],
        )

        with patch("client.engine.agent.time.sleep", return_value=None):
            run_solving_loop(cfg, env, agent, event_sink=events.append)

        self.assertEqual(
            env.step_actions,
            [GameAction.ACTION1, GameAction.ACTION3, GameAction.ACTION1],
        )
        self.assertNotIn(GameAction.RESET, env.step_actions)
        self.assertEqual(len(llm.calls), 6)
        action_events = [event for event in events if event.startswith("Action:")]
        self.assertTrue(action_events)
        self.assertIn("LLM subgoal: try the first open direction", action_events[0])
        self.assertNotIn("explore_least_seen", action_events[0])
        self.assertFalse(
            any(event.startswith("Expected observation:") for event in events)
        )


if __name__ == "__main__":
    unittest.main()
