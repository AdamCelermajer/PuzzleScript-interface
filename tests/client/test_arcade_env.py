import os
import sys
import unittest
from dataclasses import dataclass

from arcengine import GameAction as ArcGameAction, GameState as ArcGameState
import numpy as np


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from client.engine.arcade_env import ArcadeEnv  # type: ignore[import-not-found]
from client.engine.types import GameAction, GameState  # type: ignore[import-not-found]


@dataclass
class FakeActionInput:
    id: int
    data: dict


@dataclass
class FakeFrameDataRaw:
    game_id: str
    frame: list
    state: ArcGameState
    levels_completed: int
    win_levels: int
    action_input: FakeActionInput
    guid: str
    full_reset: bool
    available_actions: list[int]


class FakeEnvironmentWrapper:
    def __init__(self) -> None:
        self.stepped_actions: list[ArcGameAction] = []

    def reset(self) -> FakeFrameDataRaw:
        return FakeFrameDataRaw(
            game_id="sokoban-basic-v1",
            frame=[np.array([[0, 1], [1, 0]], dtype=np.int8)],
            state=ArcGameState.NOT_FINISHED,
            levels_completed=0,
            win_levels=2,
            action_input=FakeActionInput(id=ArcGameAction.RESET, data={}),
            guid="guid-1",
            full_reset=True,
            available_actions=[1, 2, 7],
        )

    def step(
        self, action: ArcGameAction, data=None, reasoning=None
    ) -> FakeFrameDataRaw:
        self.stepped_actions.append(action)
        return FakeFrameDataRaw(
            game_id="sokoban-basic-v1",
            frame=[np.array([[1, 0], [0, 1]], dtype=np.int8)],
            state=ArcGameState.WIN,
            levels_completed=2,
            win_levels=2,
            action_input=FakeActionInput(id=action, data=data or {}),
            guid="guid-1",
            full_reset=False,
            available_actions=[7],
        )


class FakeArcade:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.wrapper = FakeEnvironmentWrapper()
        self.make_calls: list[tuple[str, dict]] = []

    def make(self, game_id: str, **kwargs):
        self.make_calls.append((game_id, kwargs))
        return self.wrapper


class ArcadeEnvTests(unittest.TestCase):
    def test_reset_uses_arcade_wrapper_and_converts_actions(self) -> None:
        env = ArcadeEnv(
            game_id="sokoban-basic-v1",
            backend_url="http://localhost:8000",
            api_key="local-dev",
            arcade_factory=FakeArcade,
        )

        frame = env.reset()

        self.assertEqual(frame.state, GameState.PLAYING)
        self.assertEqual(frame.guid, "guid-1")
        self.assertEqual(frame.frame, [[[0, 1], [1, 0]]])
        self.assertEqual(
            frame.available_actions,
            [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION7],
        )

    def test_step_forwards_arcengine_actions_and_maps_terminal_state(self) -> None:
        env = ArcadeEnv(
            game_id="sokoban-basic-v1",
            backend_url="http://localhost:8000",
            api_key="local-dev",
            arcade_factory=FakeArcade,
        )
        env.reset()

        frame = env.step(GameAction.ACTION3)

        self.assertEqual(frame.state, GameState.WIN)
        self.assertEqual(env._env.stepped_actions, [ArcGameAction.ACTION3])
        self.assertEqual(frame.action_input.action, GameAction.ACTION3)

    def test_renderer_is_forwarded_to_arcade_make(self) -> None:
        renderer = lambda steps, frame_data: None

        env = ArcadeEnv(
            game_id="sokoban-basic-v1",
            backend_url="http://localhost:8000",
            api_key="local-dev",
            arcade_factory=FakeArcade,
            renderer=renderer,
        )

        self.assertEqual(
            env.arcade.make_calls[0],
            ("sokoban-basic-v1", {"render_mode": None, "renderer": renderer}),
        )


if __name__ == "__main__":
    unittest.main()
