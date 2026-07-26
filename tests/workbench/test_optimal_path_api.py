import time
import unittest

from fastapi.testclient import TestClient

from experiement.bfs_solver.web_manager import ACTIVE_STATUSES, OptimalPathManager
from workbench.app import create_app


def wait_finished(run, timeout=5):
    deadline = time.time() + timeout
    while run.status in ACTIVE_STATUSES and time.time() < deadline:
        time.sleep(0.02)


class OptimalPathApiTests(unittest.TestCase):
    def test_solver_progress_result_replay_and_reload_endpoint(self):
        manager = OptimalPathManager()
        client = TestClient(create_app(optimal_path_manager=manager))

        games = client.get("/api/optimal-path/games")
        self.assertEqual(games.status_code, 200)
        self.assertIn(
            "ps_sokoban_basic-v1",
            {item["game_id"] for item in games.json()["games"]},
        )

        started = client.post(
            "/api/optimal-path/runs",
            json={
                "game_id": "ps_sokoban_basic-v1",
                "timeout_seconds": 10,
                "max_states": 10_000,
            },
        )
        self.assertEqual(started.status_code, 202)
        run = manager.get(started.json()["run_id"])
        wait_finished(run)

        current = client.get("/api/optimal-path/runs/current")
        self.assertEqual(current.headers["cache-control"], "no-store")
        snapshot = current.json()["run"]
        self.assertEqual(snapshot["status"], "solved")
        self.assertEqual(snapshot["result"]["totalLevels"], 2)
        self.assertEqual(snapshot["result"]["levelsSolved"], 2)
        self.assertEqual(snapshot["result"]["solutionDepth"], 49)
        self.assertTrue(snapshot["result"]["replayVerified"])
        self.assertEqual(len(snapshot["replay"]), 51)
        self.assertTrue(snapshot["replay"][-1]["won"])
        self.assertGreater(snapshot["progress"]["transitions"], 0)
        self.assertGreaterEqual(snapshot["progress"]["maxDepthDiscovered"], 33)

    def test_unknown_game_is_rejected(self):
        client = TestClient(create_app(optimal_path_manager=OptimalPathManager()))
        response = client.post(
            "/api/optimal-path/runs",
            json={"game_id": "../missing", "timeout_seconds": 1},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
