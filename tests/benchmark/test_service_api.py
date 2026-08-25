import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from benchmark.app import create_app
from benchmark.service import BenchmarkRunManager
from benchmark.tracks.closeness import frame_key


LEVEL = {
    "level_index": 0,
    "directory": "levels/level-000",
    "solution_actions": 1,
    "replay_verified": True,
    "solution": {
        "action_count": 1,
        "actions": ["RIGHT"],
        "replay_verified": True,
    },
    "rule_probes_artifact": {
        "requested_probes": 10,
        "covered_rule_families": ["move"],
        "probes": [
            {
                "probe_id": "level-0-step-1",
                "level_index": 0,
                "before_frame": [[0, 2]],
                "action": "ACTION4",
                "expected_frame": [[2, 0]],
                "fired_rule_ids": ["move"],
                "solution_relevant": True,
            }
        ],
    },
    "closeness_artifact": {
        "mode": "replay_verified_solution_trace",
        "replay_verified": True,
        "trace": [
            {
                "frame_key": frame_key([[0, 2]]),
                "closeness": 0.0,
                "remaining_actions": 1,
            }
        ],
    },
}

CATALOG = {
    "catalog_id": "test-catalog",
    "version": "0.4.0",
    "source": {
        "scope_note": "Verified test artifacts.",
        "games_root": "test",
    },
    "games": [
        {
            "game_id": "secret-game",
            "max_actions": 10,
            "artifact_status": "replay_verified",
            "tracks": {
                "rule_learning": {"enabled": True},
                "closeness": {"enabled": True},
            },
            "levels": [LEVEL],
            "reference": {
                "scope": "artifact_level",
                "level_index": 0,
                "actions": 1,
                "path": ["RIGHT"],
                "replay_verified": True,
            },
        }
    ],
}


class FakeUpstream:
    def __init__(self):
        self.calls = []

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "/api/scorecard/open":
            return {"card_id": "upstream-card"}
        if path == "/api/cmd/RESET":
            return {
                "game_id": payload["game_id"],
                "guid": "opaque-guid",
                "frame": [[[0, 2]]],
                "rendered_frame": {"data_url": "data:image/png;base64,AA=="},
                "legend": {"2": "Player"},
                "state": "NOT_FINISHED",
                "levels_completed": 0,
                "win_levels": 1,
                "available_actions": [1, 4, 7],
            }
        if path.startswith("/api/cmd/ACTION"):
            return {
                "game_id": payload["game_id"],
                "guid": payload["guid"],
                "frame": [[[2, 0]]],
                "rendered_frame": {"data_url": "data:image/png;base64,BB=="},
                "legend": {"2": "Player"},
                "state": "WIN",
                "levels_completed": 1,
                "win_levels": 1,
                "available_actions": [7],
            }
        if path == "/api/scorecard/close":
            return {"closed": True}
        raise AssertionError((method, path, payload))


class LearningBenchmarkApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.upstream = FakeUpstream()
        self.manager = BenchmarkRunManager(
            catalog=CATALOG,
            upstream=self.upstream,
            results_dir=Path(self.tmp.name),
        )
        self.client = TestClient(create_app(self.manager))

    def tearDown(self):
        self.tmp.cleanup()

    def create_run(self, capabilities=None, representation=None):
        response = self.client.post(
            "/api/benchmark/runs",
            json={
                "capabilities": capabilities
                or ["rule_learning", "closeness"],
                "sample_size": 1,
                "seed": 7,
                "representation": representation or {},
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def headers(run):
        return {"X-API-Key": run["run_token"]}

    @staticmethod
    def monitor_headers(run):
        return {"X-Monitor-Key": run["monitor_token"]}

    def reset(self, run):
        return self.client.post(
            "/api/cmd/RESET",
            headers=self.headers(run),
            json={
                "card_id": run["run_id"],
                "game_id": "env-0001",
            },
        )

    def action(self, run, guid):
        return self.client.post(
            "/api/cmd/ACTION4",
            headers=self.headers(run),
            json={"game_id": "env-0001", "guid": guid},
        )

    def monitor(self, run):
        response = self.client.get(
            f"/api/benchmark/runs/{run['run_id']}/monitor",
            headers=self.monitor_headers(run),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_contract_and_artifact_endpoints_expose_only_two_tracks(self):
        contract = self.client.get("/api/benchmark/contract").json()
        artifacts = self.client.get("/api/benchmark/artifacts").json()

        self.assertEqual(
            set(contract["scores"]), {"rule_learning", "closeness"}
        )
        self.assertEqual(
            contract["interaction"]["challenge_checkpoints"],
            [
                "level_start",
                "every_10_actions",
                "level_complete",
                "budget_end",
            ],
        )
        self.assertEqual(artifacts["summary"]["games"], 1)
        self.assertEqual(artifacts["summary"]["rule_probes"], 1)

    def test_webpage_is_the_complete_user_facing_score_surface(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("PuzzleScript Benchmark", response.text)
        self.assertIn('id="rule-score-value"', response.text)
        self.assertIn('id="closeness-score-value"', response.text)
        self.assertIn('id="artifact-rows"', response.text)
        self.assertIn('id="run-partial-agent"', response.text)
        self.assertIn('id="run-random-agent"', response.text)
        self.assertNotIn("Goal recognition", response.text)

    def test_reset_returns_hidden_rule_challenge_and_initial_closeness(self):
        run = self.create_run()
        reset = self.reset(run)

        self.assertEqual(reset.status_code, 200, reset.text)
        body = reset.json()
        self.assertEqual(body["game_id"], "env-0001")
        self.assertNotIn("secret-game", reset.text)
        challenge = body["benchmark_challenge"]
        self.assertEqual(challenge["checkpoint"], "level_start")
        self.assertEqual(len(challenge["probes"]), 1)
        self.assertEqual(challenge["probes"][0]["before_frame"], [[0, 2]])
        self.assertEqual(challenge["probes"][0]["action"], "ACTION4")
        self.assertNotIn("expected_frame", challenge["probes"][0])

        monitor = self.monitor(run)
        closeness = monitor["environments"][0]["closeness"]
        self.assertEqual(closeness["percent"], 0.0)
        self.assertEqual(closeness["remaining_actions"], 1)

    def test_rule_challenge_submission_updates_learning_curve(self):
        run = self.create_run()
        challenge = self.reset(run).json()["benchmark_challenge"]
        probe_id = challenge["probes"][0]["probe_id"]

        response = self.client.post(
            challenge["submit_path"],
            headers=self.headers(run),
            json={
                "predictions": [
                    {
                        "probe_id": probe_id,
                        "predicted_frame": [[2, 0]],
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["score"]["summary"]["exact_frame"], 1.0
        )
        monitor = self.monitor(run)
        score = monitor["scores"]["rule_learning"]
        self.assertEqual(score["summary"]["latest_exact_frame"], 1.0)
        self.assertEqual(score["summary"]["challenges_submitted"], 1)
        self.assertEqual(len(score["learning_curve"]), 1)

    def test_level_completion_is_100_percent_and_creates_checkpoint(self):
        run = self.create_run()
        reset = self.reset(run).json()
        response = self.action(run, reset["guid"])

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            body["benchmark_challenge"]["checkpoint"], "level_complete"
        )
        monitor = self.monitor(run)
        self.assertEqual(
            monitor["scores"]["closeness"]["summary"][
                "mean_level_closeness"
            ],
            1.0,
        )
        environment = monitor["environments"][0]
        self.assertTrue(environment["completed"])
        self.assertEqual(environment["closeness"]["percent"], 100.0)

    def test_latest_unanswered_rule_challenge_counts_as_zero(self):
        run = self.create_run()
        reset = self.reset(run).json()
        first = reset["benchmark_challenge"]
        self.client.post(
            first["submit_path"],
            headers=self.headers(run),
            json={
                "predictions": [
                    {
                        "probe_id": first["probes"][0]["probe_id"],
                        "predicted_frame": [[2, 0]],
                    }
                ]
            },
        )
        self.action(run, reset["guid"])

        rule = self.monitor(run)["scores"]["rule_learning"]
        self.assertEqual(rule["summary"]["latest_exact_frame"], 0.0)
        self.assertEqual(rule["summary"]["latest_coverage"], 0.0)
        self.assertEqual(rule["summary"]["challenges_submitted"], 1)
        self.assertEqual(rule["summary"]["challenges_created"], 2)

    def test_optional_representation_fields_remain_filtered(self):
        run = self.create_run()
        plain = self.reset(run).json()
        self.assertNotIn("legend", plain)
        self.assertNotIn("rendered_frame", plain)
        self.assertNotIn("action_semantics", plain)

        second = self.create_run(
            representation={
                "rendered_image": True,
                "legend": True,
                "action_semantics": True,
            }
        )
        rich = self.reset(second).json()
        self.assertIn("rendered_frame", rich)
        self.assertEqual(rich["legend"], {"2": "Player"})
        self.assertEqual(
            rich["action_semantics"],
            {"ACTION1": "Up", "ACTION4": "Right", "ACTION7": "Undo"},
        )

    def test_monitor_has_separate_auth_and_reveals_evaluator_identity(self):
        run = self.create_run()
        self.reset(run)

        unauthorized = self.client.get(
            f"/api/benchmark/runs/{run['run_id']}/monitor",
            headers=self.headers(run),
        )
        authorized = self.monitor(run)

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(
            authorized["environments"][0]["game_id"], "secret-game"
        )

    def test_agent_scorecard_stays_opaque(self):
        run = self.create_run()
        response = self.client.get(
            f"/api/scorecard/{run['run_id']}",
            headers=self.headers(run),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("secret-game", response.text)
        self.assertEqual(response.json()["games"], [{"alias": "env-0001"}])

    def test_close_persists_both_scores_and_reveals_identity(self):
        run = self.create_run()
        self.reset(run)
        response = self.client.post(
            f"/api/benchmark/runs/{run['run_id']}/close",
            headers=self.headers(run),
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(
            set(result["scores"]), {"rule_learning", "closeness"}
        )
        self.assertEqual(result["games"][0]["game_id"], "secret-game")
        self.assertTrue(
            (Path(self.tmp.name) / f"{run['run_id']}.json").exists()
        )

    def test_action_budget_is_enforced(self):
        manager = BenchmarkRunManager(
            catalog={
                **CATALOG,
                "games": [{**CATALOG["games"][0], "max_actions": 1}],
            },
            upstream=self.upstream,
            results_dir=Path(self.tmp.name),
        )
        client = TestClient(create_app(manager))
        run = client.post(
            "/api/benchmark/runs",
            json={
                "capabilities": ["closeness"],
                "sample_size": 1,
                "seed": 0,
            },
        ).json()
        headers = self.headers(run)
        reset = client.post(
            "/api/cmd/RESET",
            headers=headers,
            json={"card_id": run["run_id"], "game_id": "env-0001"},
        ).json()
        first = client.post(
            "/api/cmd/ACTION4",
            headers=headers,
            json={"game_id": "env-0001", "guid": reset["guid"]},
        )
        second = client.post(
            "/api/cmd/ACTION4",
            headers=headers,
            json={"game_id": "env-0001", "guid": reset["guid"]},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertIn("Action budget exhausted", second.text)


if __name__ == "__main__":
    unittest.main()
