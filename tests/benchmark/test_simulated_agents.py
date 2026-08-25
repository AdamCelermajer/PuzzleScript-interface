import random
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from benchmark.agents import RandomAgent
from benchmark.app import create_app
from benchmark.catalog import load_catalog
from benchmark.service import BenchmarkRunManager


class ArtifactReplayUpstream:
    def __init__(self, catalog):
        self.catalog = {
            str(game["game_id"]): game for game in catalog["games"]
        }
        self.sessions = {}
        self.next_guid = 1

    def request(self, method, path, payload=None):
        if path == "/api/scorecard/open":
            return {"card_id": "fixture-card"}
        if path == "/api/cmd/RESET":
            game_id = str(payload["game_id"])
            guid = f"fixture-guid-{self.next_guid}"
            self.next_guid += 1
            self.sessions[guid] = {"game_id": game_id, "step": 0}
            return self._observation(guid, completed=False)
        if path.startswith("/api/cmd/ACTION"):
            session = self.sessions[str(payload["guid"])]
            session["step"] += 1
            game = self.catalog[session["game_id"]]
            completed = session["step"] >= int(
                game["reference"]["actions"]
            )
            return self._observation(str(payload["guid"]), completed)
        if path == "/api/scorecard/close":
            return {"closed": True}
        raise AssertionError((method, path, payload))

    def _observation(self, guid, completed):
        session = self.sessions[guid]
        game = self.catalog[session["game_id"]]
        trace = game["levels"][0]["closeness_artifact"]["trace"]
        trace_index = min(session["step"], len(trace) - 1)
        return {
            "game_id": session["game_id"],
            "guid": guid,
            "frame": [trace[trace_index]["frame"]],
            "state": "WIN" if completed else "NOT_FINISHED",
            "levels_completed": 1 if completed else 0,
            "win_levels": 1,
            "available_actions": [1, 2, 3, 4, 5, 7],
        }


class ReferenceAgentTests(unittest.TestCase):
    def test_random_agent_uses_only_advertised_ordinary_actions(self):
        agent = RandomAgent()
        observation = {"available_actions": [2, 4, 7]}
        choices = {
            agent.select_action(observation, random.Random(seed))
            for seed in range(20)
        }

        self.assertEqual(choices, {"ACTION2", "ACTION4"})

    def test_fixed_partial_agent_produces_repeatable_partial_scores(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as tmp:
            manager = BenchmarkRunManager(
                catalog=catalog,
                upstream=ArtifactReplayUpstream(catalog),
                results_dir=Path(tmp),
            )
            response = TestClient(create_app(manager)).post(
                "/api/benchmark/simulated-partial-agent"
            )
            self.assertEqual(response.status_code, 201, response.text)
            payload = response.json()
            monitor = manager.monitor(
                payload["run_id"], payload["monitor_token"]
            )

        self.assertEqual(payload["status"], "closed")
        self.assertEqual(
            payload["simulation"]["scenario_id"],
            "fixed-partial-success-v1",
        )
        self.assertEqual(len(monitor["environments"]), 3)
        rule = monitor["scores"]["rule_learning"]["summary"]
        closeness = monitor["scores"]["closeness"]["summary"]
        self.assertEqual(rule["latest_exact_frame"], 0.533333)
        self.assertEqual(rule["challenges_submitted"], 7)
        self.assertEqual(closeness["mean_level_closeness"], 0.700337)
        self.assertEqual(closeness["coverage"], 1.0)
        self.assertEqual(
            sum(item["completed"] for item in monitor["environments"]), 1
        )

    def test_live_agent_endpoints_return_before_background_play_finishes(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as tmp:
            manager = BenchmarkRunManager(
                catalog=catalog,
                upstream=ArtifactReplayUpstream(catalog),
                results_dir=Path(tmp),
            )
            client = TestClient(create_app(manager))
            for path in (
                "/api/benchmark/simulated-partial-agent/live?delay_seconds=0",
                "/api/benchmark/random-agent/live?delay_seconds=0",
            ):
                response = client.post(path)
                self.assertEqual(response.status_code, 201, response.text)
                run_id = response.json()["run_id"]
                deadline = time.monotonic() + 2
                while (
                    manager.get(run_id).status not in {"closed", "error"}
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                run = manager.get(run_id)
                self.assertEqual(run.status, "closed")
                self.assertTrue(
                    any(event["type"] == "action" for event in run.events)
                )


if __name__ == "__main__":
    unittest.main()
