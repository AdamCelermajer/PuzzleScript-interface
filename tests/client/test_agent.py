import os
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
from client.engine.types import ActionInput, FrameData, GameAction, GameState


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
        game_id="sokoban-basic-v1",
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
        model_type: str = "flash",
        json_mode: bool = False,
    ) -> str:
        self.calls.append((system, prompt, model_type, json_mode))
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        return self.responses.pop(0)


class AgentLoopTests(unittest.TestCase):
    def _make_config(self, *, max_steps: int = 2, mode: str = "learn") -> Config:
        tmpdir = tempfile.mkdtemp()
        return Config(
            api_key="test-key",
            game="sokoban-basic-v1",
            max_steps=max_steps,
            mode=mode,
            rules_dir=tmpdir,
        )

    def test_learning_loop_uses_llm_actions_each_turn(self) -> None:
        cfg = self._make_config(max_steps=2, mode="learn")
        llm = FakeLlmClient(
            [
                "ACTION4",
                "ACTION2",
                '{"final_rules": {}, "legend": {}, "final_goal": ""}',
            ]
        )
        agent = Agent(cfg, llm)
        env = FakeEnv(
            reset_frames=[_frame(frame=[[[0, 0], [0, 0]]])],
            step_frames=[
                _frame(action=GameAction.ACTION4, frame=[[[0, 1], [0, 0]]]),
                _frame(action=GameAction.ACTION2, frame=[[[0, 1], [0, 1]]]),
            ],
        )

        with patch("client.engine.agent.time.sleep", return_value=None):
            run_learning_loop(cfg, env, agent)

        self.assertEqual(env.step_actions, [GameAction.ACTION4, GameAction.ACTION2])
        self.assertEqual(len(llm.calls), 3)

    def test_solving_loop_uses_simple_non_llm_placeholder_actions(self) -> None:
        cfg = self._make_config(max_steps=3, mode="solve")
        llm = FakeLlmClient([])
        agent = Agent(cfg, llm)
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
            run_solving_loop(cfg, env, agent)

        self.assertEqual(
            env.step_actions,
            [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3],
        )
        self.assertNotIn(GameAction.RESET, env.step_actions)
        self.assertEqual(llm.calls, [])


if __name__ == "__main__":
    unittest.main()
