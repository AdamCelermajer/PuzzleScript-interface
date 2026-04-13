import os
import random
import subprocess
import sys
import time
import unittest

import arc_agi
import requests
from arc_agi import OperationMode
from arcengine import GameState as ArcGameState


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from client.engine.arcade_env import ArcadeEnv  # type: ignore[import-not-found]
from client.engine.types import GameAction, GameState  # type: ignore[import-not-found]


NODE_PORT = 3101
ARC_PORT = 8100


def wait_for_http(url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code in {200, 400, 404}:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise AssertionError(f"Service did not become ready: {url}")


@unittest.skipUnless(
    os.environ.get("RUN_LOCAL_ARC_STACK_TESTS") == "1", "Local stack test is opt-in"
)
class LocalArcStackTests(unittest.TestCase):
    def test_toolkit_backed_env_can_talk_to_local_puzzlescript_arc_service(
        self,
    ) -> None:
        node_server = subprocess.Popen(
            ["node", "puzzlescript_interface/runtime/server.js"],
            cwd=ROOT,
            env={**os.environ, "PORT": str(NODE_PORT)},
        )
        arc_service = subprocess.Popen(
            [sys.executable, "puzzlescript_interface/api/main.py"],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": ROOT,
                "ARC_PROXY_PORT": str(ARC_PORT),
                "PUZZLESCRIPT_SERVER_URL": f"http://127.0.0.1:{NODE_PORT}",
            },
        )

        try:
            wait_for_http(f"http://127.0.0.1:{NODE_PORT}/observe?sessionId=missing")
            wait_for_http(f"http://127.0.0.1:{ARC_PORT}/api/games")

            env = ArcadeEnv(
                game_id="ps_sokoban_basic-v1",
                backend_url=f"http://127.0.0.1:{ARC_PORT}",
                api_key="local-dev",
            )

            frame = env.reset()
            self.assertEqual(frame.state, GameState.PLAYING)
            self.assertEqual(frame.win_levels, 2)
            self.assertEqual(frame.game_id, "ps_sokoban_basic-v1")

            next_frame = env.step(GameAction.ACTION4)
            self.assertIn(next_frame.state, {GameState.PLAYING, GameState.WIN})
        finally:
            arc_service.terminate()
            node_server.terminate()
            arc_service.wait(timeout=10)
            node_server.wait(timeout=10)

    def test_doc_style_random_client_can_play_multiple_games(self) -> None:
        node_server = subprocess.Popen(
            ["node", "puzzlescript_interface/runtime/server.js"],
            cwd=ROOT,
            env={**os.environ, "PORT": str(NODE_PORT)},
        )
        arc_service = subprocess.Popen(
            [sys.executable, "puzzlescript_interface/api/main.py"],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": ROOT,
                "ARC_PROXY_PORT": str(ARC_PORT),
                "PUZZLESCRIPT_SERVER_URL": f"http://127.0.0.1:{NODE_PORT}",
            },
        )

        try:
            wait_for_http(f"http://127.0.0.1:{NODE_PORT}/observe?sessionId=missing")
            wait_for_http(f"http://127.0.0.1:{ARC_PORT}/api/games")

            arc = arc_agi.Arcade(
                operation_mode=OperationMode.ONLINE,
                arc_base_url=f"http://127.0.0.1:{ARC_PORT}",
                arc_api_key="local-dev",
            )
            available_games = {env.game_id for env in arc.get_environments()}
            target_games = [
                game_id
                for game_id in [
                    "ps_sokoban_basic-v1",
                    "ps_1_2_3_ban-v1",
                    "ps_midas-v1",
                ]
                if game_id in available_games
            ]

            self.assertEqual(len(target_games), 3)

            rng = random.Random(0)
            steps_per_game = 8

            for game_id in target_games:
                env = arc.make(game_id)
                self.assertIsNotNone(env, msg=f"arc.make failed for {game_id}")

                obs = env.reset()
                self.assertIsNotNone(obs, msg=f"reset failed for {game_id}")

                for _ in range(steps_per_game):
                    self.assertTrue(
                        env.action_space, msg=f"No actions available for {game_id}"
                    )
                    action = rng.choice(env.action_space)
                    action_data = {}
                    if action.is_complex():
                        action_data = {
                            "x": rng.randint(0, 63),
                            "y": rng.randint(0, 63),
                        }

                    obs = env.step(action, data=action_data)
                    self.assertIsNotNone(obs, msg=f"step failed for {game_id}")

                    if obs.state == ArcGameState.WIN:
                        break
                    if obs.state == ArcGameState.GAME_OVER:
                        obs = env.reset()
                        self.assertIsNotNone(
                            obs, msg=f"reset after GAME_OVER failed for {game_id}"
                        )

            scorecard = arc.get_scorecard()
            self.assertIsNotNone(scorecard)
            self.assertGreaterEqual(len(scorecard.environments), len(target_games))
        finally:
            arc_service.terminate()
            node_server.terminate()
            arc_service.wait(timeout=10)
            node_server.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
