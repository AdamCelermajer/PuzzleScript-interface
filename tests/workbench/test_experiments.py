import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.catalog import discover, run_path, snapshot
from workbench.experiments import ExperimentRequest, create_router, plan_runs, write_json
from workbench.experiment_job import run_job


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path.parent

    def test_catalog_finds_nested_campaigns_and_does_not_scan_controller_copies(self):
        live = self.put("output/batch/repairs/game/campaign/evolution_config.json", {"profile_settings": {"game_id": "actual"}})
        self.put("output/batch/controller/avo/output/evolution/copied/evolution_config.json", {"profile_settings": {"game_id": "copied"}})
        self.put("avo/output/evolution/old/evolution_config.json", {"profile_settings": {"game_id": "old"}})
        self.put("avo/output/evolution/old/optimizer_analysis/session.json", {"status": "running"})
        data = snapshot(self.root, {str(live.parent.resolve()).casefold(): "avo-isolated-test"})
        self.assertEqual(len(data["runs"]), 2)
        self.assertEqual(data["runs"][0]["game_id"], "actual")
        self.assertEqual(data["runs"][0]["status"], "running")
        self.assertEqual(data["runs"][1]["status"], "unconfirmed")
        self.assertIsNone(data["runs"][0]["best_fitness"])

    def test_completion_does_not_invent_a_win_or_use_research_fitness(self):
        path = self.put("output/batch/game/campaign/evolution_config.json", {"profile_settings": {"game_id": "ps_purple-v1"}})
        self.put("output/batch/game/campaign/evolution_summary.json", {"success": False})
        self.put("output/batch/game/campaign/lineage.json", {"evaluations": [{"fitness": 0, "success": False}]})
        self.put("output/batch/game/campaign/x_0001/research/final_summary.json", {"fitness": 99, "success": True})
        row = snapshot(self.root, {})["runs"][0]
        self.assertEqual(row["status"], "completed")
        self.assertFalse(row["solved"])
        self.assertEqual(row["best_fitness"], 0)

    def test_paths_deny_traversal_absolute_paths_and_links(self):
        for value in ("../.env", "output/../.env", "/output/a", "C:/private", "output\\a"):
            with self.assertRaises(ValueError):
                run_path(value, self.root)
        outside = self.root / "private"
        outside.mkdir()
        (self.root / "output").mkdir()
        try:
            (self.root / "output/link").symlink_to(outside, target_is_directory=True)
        except OSError:
            return
        with self.assertRaises(ValueError):
            run_path("output/link/file.json", self.root)

    def test_parallel_avo_plan_has_distinct_outputs_and_independent_efforts(self):
        request = ExperimentRequest(kind="avo", game_ids=["one", "two"], models=["gpt-5.6-luna"], efforts=["high"], repeats=2, parallel=3, optimizer_effort="low")
        rows = plan_runs(request, self.root / "output/workbench/job", self.root)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r["output"] for r in rows}), 4)
        for row in rows:
            command = row["command"]
            self.assertEqual(command[command.index("--optimizer-effort") + 1], "low")
            self.assertEqual(command[command.index("--player-effort") + 1], "high")
            self.assertIn("avo.docker.launch", command)
        self.assertFalse((self.root / "output").exists())

    def test_direct_player_matrix_and_continuation_constraints(self):
        request = ExperimentRequest(kind="codex", game_ids=["one"], models=["sol", "luna"], efforts=["low", "high"], conditions=["baseline", "baseline-plus"], repeats=2)
        rows = plan_runs(request, self.root / "output/workbench/job", self.root)
        self.assertEqual(len(rows), 16)
        self.assertTrue(all("--no-window" in r["command"] for r in rows))
        with self.assertRaises(ValueError):
            ExperimentRequest(kind="codex", game_ids=["one"], repeats=2, continue_from="output/parent")

    def test_stale_worker_and_queued_records_are_not_reported_live(self):
        self.put("output/workbench/job/job.json", {"status": "running", "heartbeat": time.time()-60,
            "config": {"kind": "avo"}, "runs": [{"id": "output/workbench/job/run-0001/campaign", "kind": "avo", "status": "running"}]})
        data = snapshot(self.root, {})
        self.assertEqual(data["jobs"][0]["status"], "unconfirmed")
        self.assertFalse(data["jobs"][0]["can_stop"])
        self.assertEqual(data["runs"][0]["status"], "unconfirmed")

    def client(self):
        app = FastAPI()
        app.include_router(create_router(self.root))
        return TestClient(app)

    def test_api_preview_never_starts_a_process_and_rejects_bad_budget(self):
        with self.client() as client, patch("workbench.experiments.subprocess.Popen") as popen:
            response = client.post("/api/workbench/experiments/preview", json={"kind":"avo", "game_ids":["a","b"], "parallel":2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 2)
            popen.assert_not_called()
            self.assertEqual(client.post("/api/workbench/experiments", json={"kind":"avo", "game_ids":["a"], "parallel":0}).status_code, 422)

    def test_stop_only_targets_owned_job_and_artifacts_are_allowlisted(self):
        self.put("output/workbench/owned/job.json", {"runs":[]})
        self.put("output/other/job.json", {"runs":[]})
        self.put("output/codex/run_config.json", {"condition":"baseline"})
        self.put("output/codex/auth.json", {"secret":"never returned"})
        with self.client() as client:
            self.assertEqual(client.post("/api/workbench/experiments/stop", params={"job":"output/other"}).status_code, 400)
            self.assertEqual(client.post("/api/workbench/experiments/stop", params={"job":"output/workbench/owned"}).status_code, 202)
            self.assertTrue((self.root / "output/workbench/owned/stop.request").exists())
            self.assertEqual(client.get("/api/workbench/record/file", params={"run":"output/codex", "file":"auth.json"}).status_code, 400)

    def test_worker_runs_bounded_children_and_records_failure(self):
        directory = self.root / "output/workbench/job"
        directory.mkdir(parents=True)
        rows = [{"id":str(i), "kind":"codex", "output":str(directory/f"run-{i}"), "command":[sys.executable,"-c",f"import sys; sys.exit({i})"], "status":"queued"} for i in (0,1)]
        write_json(directory / "job.json", {"config":{"parallel":1,"max_hours":.1},"runs":rows})
        run_job(directory)
        data = json.loads((directory / "job.json").read_text())
        self.assertEqual(data["status"], "failed")
        self.assertEqual([r["status"] for r in data["runs"]], ["completed", "failed"])

    def test_cancellation_does_not_start_queued_children(self):
        directory = self.root / "output/workbench/job"
        directory.mkdir(parents=True)
        write_json(directory / "job.json", {"config":{"parallel":1,"max_hours":.1}, "runs":[{"status":"queued"}]})
        (directory / "stop.request").touch()
        with patch("workbench.experiment_job.subprocess.Popen") as popen:
            run_job(directory)
            popen.assert_not_called()
        self.assertEqual(json.loads((directory / "job.json").read_text())["status"], "cancelled")

    def test_running_child_is_stopped_and_remaining_work_cancelled(self):
        directory = self.root / "output/workbench/job"
        directory.mkdir(parents=True)
        signal_path = directory / "stop.request"
        command = [sys.executable, "-c", "from pathlib import Path; import time; Path(" + repr(str(signal_path)) + ").touch(); time.sleep(60)"]
        rows = [{"id":str(i), "kind":"codex", "output":str(directory/f"run-{i}"), "command":command, "status":"queued"} for i in (0,1)]
        write_json(directory / "job.json", {"config":{"parallel":1,"max_hours":.1},"runs":rows})
        run_job(directory)
        data = json.loads((directory / "job.json").read_text())
        self.assertEqual(data["status"], "cancelled")
        self.assertTrue(all(r["status"] == "cancelled" for r in data["runs"]))
        self.assertNotIn("pid", data["runs"][1])

    def test_docker_launch_preserves_role_settings_and_cleans_temporary_credentials(self):
        from avo.docker import launch
        auth_dir = self.root / "fake-codex"
        auth_dir.mkdir()
        (auth_dir / "auth.json").write_text(json.dumps({"tokens":{"dummy":"test-only"}}))
        output = self.root / "new-campaign"
        calls = []

        def subprocess_run(command, **kwargs):
            calls.append(command)
            if command[:2] == ["docker", "run"]:
                (output / "isolation_preflight.json").write_text('{"passed":true}')
            return subprocess.CompletedProcess(command, 0)

        args = ["launch", "--campaign", "--output-dir", str(output), "--game-id", "test-game",
                "--backend-url", "http://host.docker.internal:8000", "--optimizer-model", "outer",
                "--player-model", "inner", "--optimizer-effort", "low", "--player-effort", "high",
                "--max-evaluations", "2", "--research-moves", "30", "--solver-moves", "50"]
        with patch.object(sys, "argv", args), patch.dict("os.environ", {"CODEX_HOME":str(auth_dir)}), patch.object(launch, "stage_controller"), patch.object(launch.subprocess, "run", side_effect=subprocess_run):
            launch.main()
        self.assertEqual(calls[0][calls[0].index("--optimizer-effort")+1], "low")
        self.assertEqual(calls[0][calls[0].index("--player-effort")+1], "high")
        self.assertEqual(calls[-1][:3], ["docker", "rm", "-f"])
        self.assertEqual(calls[-1][-1], json.loads((output / "launcher.json").read_text())["container"])
        credential_mount = next(x for x in calls[0] if "dst=/credentials," in x)
        credentials = Path(credential_mount.split("src=",1)[1].split(",dst=",1)[0])
        self.assertFalse(credentials.exists())


if __name__ == "__main__":
    unittest.main()
