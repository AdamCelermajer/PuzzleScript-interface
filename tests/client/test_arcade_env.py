import os
import sys
import unittest
from dataclasses import dataclass

from arcengine import GameAction as ArcGameAction, GameState as ArcGameState
import numpy as np


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from client.arc.arcade_env import ArcadeEnv  # type: ignore[import-not-found]
from client.arc.types import GameAction, GameState  # type: ignore[import-not-found]


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
    rendered_frame: dict | None = None


class FakeEnvironmentWrapper:
    def __init__(self) -> None:
        self.stepped_actions: list[ArcGameAction] = []
        self.reset_calls = 0

    def reset(self) -> FakeFrameDataRaw:
        self.reset_calls += 1
        return FakeFrameDataRaw(
            game_id="ps_sokoban_basic-v1",
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
            game_id="ps_sokoban_basic-v1",
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


class FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeHttpSession:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        if url.endswith("/api/scorecard/open"):
            return FakeHttpResponse({"card_id": "card-1"})
        if url.endswith("/api/cmd/RESET"):
            return FakeHttpResponse(
                {
                    "game_id": "ps_sokoban_basic-v1",
                    "guid": "guid-1",
                    "frame": [[[0, 1], [1, 0]]],
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "win_levels": 2,
                    "action_input": {"id": 0, "data": {}},
                    "available_actions": [1, 2, 7],
                    "rendered_frame": {
                        "mime_type": "image/png",
                        "data_url": "data:image/png;base64,iVBORw0KGgo=",
                        "width": 10,
                        "height": 10,
                    },
                }
            )
        raise AssertionError(f"Unexpected request: {method} {url}")


class ArcadeEnvTests(unittest.TestCase):
    def test_reset_uses_arcade_wrapper_and_converts_actions(self) -> None:
        env = ArcadeEnv(
            game_id="ps_sokoban_basic-v1",
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
        self.assertEqual(env._env.reset_calls, 1)

    def test_init_does_not_keep_wrapper_auto_reset_as_visible_turn(self) -> None:
        env = ArcadeEnv(
            game_id="ps_sokoban_basic-v1",
            backend_url="http://localhost:8000",
            api_key="local-dev",
            arcade_factory=FakeArcade,
        )

        self.assertEqual(env._env.reset_calls, 0)

    def test_step_forwards_arcengine_actions_and_maps_terminal_state(self) -> None:
        env = ArcadeEnv(
            game_id="ps_sokoban_basic-v1",
            backend_url="http://localhost:8000",
            api_key="local-dev",
            arcade_factory=FakeArcade,
        )
        env.reset()

        frame = env.step(GameAction.ACTION3)

        self.assertEqual(frame.state, GameState.WIN)
        self.assertEqual(env._env.stepped_actions, [ArcGameAction.ACTION3])
        self.assertEqual(frame.action_input.action, GameAction.ACTION3)

    def test_step_forwards_click_data(self) -> None:
        env = ArcadeEnv(
            game_id="ps_sokoban_basic-v1",
            backend_url="http://localhost:8000",
            api_key="local-dev",
            arcade_factory=FakeArcade,
        )
        env.reset()

        frame = env.step(GameAction.ACTION6, data={"x": 1, "y": 0})

        self.assertEqual(env._env.stepped_actions, [ArcGameAction.ACTION6])
        self.assertEqual(frame.action_input.data, {"x": 1, "y": 0})

    def test_renderer_is_forwarded_to_arcade_make(self) -> None:
        renderer = lambda steps, frame_data: None

        env = ArcadeEnv(
            game_id="ps_sokoban_basic-v1",
            backend_url="http://localhost:8000",
            api_key="local-dev",
            arcade_factory=FakeArcade,
            renderer=renderer,
        )

        self.assertEqual(
            env.arcade.make_calls[0],
            ("ps_sokoban_basic-v1", {"render_mode": None}),
        )

    def test_convert_frame_preserves_optional_rendered_frame(self) -> None:
        env = ArcadeEnv.__new__(ArcadeEnv)
        env.game_id = "ps_sokoban_basic-v1"
        raw = FakeFrameDataRaw(
            game_id="ps_sokoban_basic-v1",
            frame=[np.array([[0]], dtype=np.int8)],
            state=ArcGameState.NOT_FINISHED,
            levels_completed=0,
            win_levels=1,
            action_input=FakeActionInput(id=ArcGameAction.RESET, data={}),
            guid="guid-1",
            full_reset=True,
            available_actions=[1],
            rendered_frame={
                "mime_type": "image/png",
                "data_url": "data:image/png;base64,iVBORw0KGgo=",
                "width": 10,
                "height": 10,
            },
        )

        converted = env._convert_frame(raw)

        self.assertIsNotNone(converted.rendered_frame)
        self.assertEqual(converted.rendered_frame.mime_type, "image/png")
        self.assertTrue(
            converted.rendered_frame.data_url.startswith("data:image/png;base64,")
        )
        self.assertEqual(converted.rendered_frame.width, 10)
        self.assertEqual(converted.rendered_frame.height, 10)

    def test_local_backend_preserves_rendered_frame_without_arc_toolkit(self) -> None:
        session = FakeHttpSession()
        env = ArcadeEnv(
            game_id="ps_sokoban_basic-v1",
            backend_url="http://127.0.0.1:8601",
            api_key="local-dev",
            http_session=session,
        )

        frame = env.reset()

        self.assertIsNotNone(frame.rendered_frame)
        self.assertEqual(frame.rendered_frame.mime_type, "image/png")
        self.assertEqual(frame.rendered_frame.width, 10)
        self.assertEqual(frame.rendered_frame.height, 10)
        self.assertTrue(
            any(url.endswith("/api/cmd/RESET") for _method, url, _kwargs in session.requests)
        )


if __name__ == "__main__":
    unittest.main()
