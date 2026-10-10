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
from workbench.experiments import ExperimentRequest, create_router, plan_runs, prepare_avo_recovery, write_json
from workbench.experiment_job import run_job


class ExperimentTests(unittest.TestCase):
    def test_backend_failure_is_visible_and_not_resumable(self):
        from workbench.catalog import snapshot

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            batch = root / "output/workbench/sample"
            output = batch / "run-0001"
            campaign = output / "campaign"
            campaign.mkdir(parents=True)
            write_json(campaign / "evolution_config.json", {
                "profile_settings": {"game_id": "ps_enqueue-v1"}, "max_evaluations": 20,
            })
            write_json(campaign / "error.json", {
                "status": "needs_assistance", "kind": "puzzlescript_backend_failure",
                "error": "PuzzleScript backend failure: HTTP 500 during ACTION5",
            })
            write_json(batch / "job.json", {
                "status": "failed", "config": {"kind": "avo"}, "runs": [{
                    "id": "output/workbench/sample/run-0001/campaign",
                    "output": str(output), "status": "failed", "kind": "avo",
                }],
            })
            catalog = snapshot(root, containers={})
        self.assertTrue(catalog["runs"][0]["needs_assistance"])
        self.assertEqual(catalog["runs"][0]["status"], "failed")
        self.assertTrue(catalog["jobs"][0]["needs_assistance"])
        self.assertFalse(catalog["jobs"][0]["can_resume"])

    def test_enqueue_requires_its_dedicated_backend_and_separate_launch(self):
        with self.assertRaisesRegex(ValueError, "dedicated backend on port 8001"):
            ExperimentRequest(kind="avo", game_ids=["ps_enqueue-v1"], backend_url="http://host.docker.internal:8000")
        with self.assertRaisesRegex(ValueError, "launch it separately"):
            ExperimentRequest(kind="avo", game_ids=["ps_enqueue-v1", "ps_icecrates-v1"], backend_url="http://host.docker.internal:8001")
        request = ExperimentRequest(kind="avo", game_ids=["ps_enqueue-v1"], backend_url="http://host.docker.internal:8001")
        self.assertEqual(request.backend_url, "http://host.docker.internal:8001")

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

    def test_missing_required_final_report_is_a_failed_campaign_with_solver_win_preserved(self):
        self.put("output/batch/game/campaign/evolution_config.json", {"world_model_mode": "final-only"})
        self.put("output/batch/game/campaign/evolution_summary.json", {
            "status": "failed", "success": False, "solver_success": True,
            "world_model": {"status": "missing"},
        })
        self.put("output/batch/game/campaign/lineage.json", {
            "evaluations": [{"fitness": 6, "success": True}],
        })
        row = snapshot(self.root, {})["runs"][0]
        self.assertEqual(row["status"], "failed")
        self.assertTrue(row["solved"])
        self.assertEqual(row["best_fitness"], 6)
        self.put("output/batch/game/campaign/evolution_summary.json", {"success": True})
        legacy_row = snapshot(self.root, {})["runs"][0]
        self.assertEqual(legacy_row["status"], "failed")
        self.assertEqual(legacy_row["status_source"], "Required final world_model.md missing")

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
        request = ExperimentRequest(kind="avo", game_ids=["one", "two"], models=["gpt-5.6-luna"], efforts=["high"], repeats=2, parallel=3, optimizer_effort="low", optimizer_service_tier="priority")
        rows = plan_runs(request, self.root / "output/workbench/job", self.root)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r["output"] for r in rows}), 4)
        for row in rows:
            command = row["command"]
            self.assertEqual(command[command.index("--optimizer-effort") + 1], "low")
            self.assertEqual(command[command.index("--optimizer-service-tier") + 1], "priority")
            self.assertEqual(command[command.index("--player-effort") + 1], "high")
            self.assertIn("avo.docker.launch", command)
        self.assertFalse((self.root / "output").exists())

    def test_deepseek_max_plan_preserves_both_efforts_and_full_trace(self):
        model = "openrouter/deepseek/deepseek-v4.1-flash"
        request = ExperimentRequest(kind="avo", game_ids=["ps_modality-v1", "ps_knightoban-v1", "ps_icecrates-v1"],
                                    models=[model], efforts=["max"], optimizer_model=model,
                                    optimizer_effort="max", trace_detail="full", max_evaluations=15,
                                    research_moves=300, solver_moves=1500, parallel=3)
        rows = plan_runs(request, self.root / "output/workbench/job", self.root)
        self.assertEqual(len(rows), 3)
        for row in rows:
            command = row["command"]
            self.assertEqual(command[command.index("--optimizer-effort") + 1], "max")
            self.assertEqual(command[command.index("--player-effort") + 1], "max")
            self.assertEqual(command[command.index("--trace-detail") + 1], "full")
            self.assertEqual(command[command.index("--research-moves") + 1], "300")

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

    def test_stale_job_reconciles_only_when_all_children_have_terminal_artifacts(self):
        runs = [
            {"id": "output/workbench/job/run-0001/campaign", "output": "output/workbench/job/run-0001/campaign", "kind": "avo", "status": "running"},
            {"id": "output/workbench/job/run-0002/campaign", "output": "output/workbench/job/run-0002/campaign", "kind": "avo", "status": "running"},
        ]
        self.put("output/workbench/job/job.json", {"status": "running", "heartbeat": time.time()-60,
            "config": {"kind": "avo"}, "runs": runs})
        for number in (1, 2):
            self.put(f"output/workbench/job/run-{number:04d}/campaign/evolution_config.json", {})
        self.put("output/workbench/job/run-0001/campaign/evolution_summary.json", {"success": True})

        incomplete = snapshot(self.root, {})
        self.assertEqual(incomplete["jobs"][0]["status"], "unconfirmed")

        self.put("output/workbench/job/run-0002/campaign/evolution_summary.json", {"success": False})
        complete = snapshot(self.root, {})
        self.assertEqual(complete["jobs"][0]["status"], "completed")
        self.assertEqual(complete["jobs"][0]["status_source"], "Terminal child artifacts")

    def test_stale_job_reconciles_to_failed_when_a_child_has_an_error_artifact(self):
        runs = [{"id": "output/workbench/job/run-0001/campaign", "output": "output/workbench/job/run-0001/campaign", "kind": "avo", "status": "running"}]
        self.put("output/workbench/job/job.json", {"status": "running", "heartbeat": time.time()-60,
            "config": {"kind": "avo"}, "runs": runs})
        self.put("output/workbench/job/run-0001/campaign/evolution_config.json", {})
        self.put("output/workbench/job/run-0001/campaign/error.json", {"error": "boom"})

        data = snapshot(self.root, {})
        self.assertEqual(data["jobs"][0]["status"], "failed")
        self.assertEqual(data["jobs"][0]["status_source"], "Terminal child artifacts")

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

    def test_record_serves_only_numbered_frame_pngs(self):
        run = self.put("output/codex/run_config.json", {"condition": "baseline-plus"})
        (run / "frames").mkdir()
        image = b"\x89PNG\r\n\x1a\nframe"
        (run / "frames/000.png").write_bytes(image)
        (run / "frames/auth.png").write_bytes(image)
        with self.client() as client:
            response = client.get("/api/workbench/record/file", params={"run": "output/codex", "file": "frames/000.png"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, image)
            self.assertEqual(response.headers["content-type"], "image/png")
            self.assertNotIn("attachment", response.headers.get("content-disposition", ""))
            for name in ("frames/auth.png", "frames/000.json", "frames/../auth.json", "model_requests/000.png"):
                self.assertEqual(client.get("/api/workbench/record/file", params={"run": "output/codex", "file": name}).status_code, 400)

    def test_pause_and_resume_api_create_a_separate_normal_tier_recovery(self):
        source = self.root / "output/workbench/owned"
        campaign = source / "run-0001/campaign"
        saved = {"profile_settings":{"game_id":"game", "backend_url":"http://host.docker.internal:8000"},
                 "player":{"model":"gpt-6-astra", "effort":"low", "max_environment_steps":30},
                 "optimizer_model":"gpt-6-astra", "optimizer_effort":"high", "max_evaluations":2,
                 "fresh_solver_max_environment_steps":50, "max_wall_seconds":600, "world_model_mode":"final-only"}
        self.put("output/workbench/owned/run-0001/campaign/evolution_config.json", saved)
        self.put("output/workbench/owned/run-0001/campaign/lineage.json", {"candidates":[], "evaluations":[]})
        row = {"id":"output/workbench/owned/run-0001/campaign", "output":str(source / "run-0001"),
               "kind":"avo", "game_id":"game", "model":"gpt-6-astra", "effort":"low",
               "world_model_mode":"final-only", "status":"paused"}
        self.put("output/workbench/owned/job.json", {"status":"paused", "config":{"kind":"avo", "parallel":1,
                 "max_hours":1, "service_tier":"priority", "optimizer_service_tier":"priority"}, "runs":[row]})
        with self.client() as client, patch("workbench.experiments.subprocess.Popen") as popen:
            response = client.post("/api/workbench/experiments/resume", params={"job":"output/workbench/owned"},
                                   json={"service_tier":"", "optimizer_service_tier":""})
        self.assertEqual(response.status_code, 202)
        popen.assert_called_once()
        recovery_id = response.json()["id"]
        recovery = json.loads((self.root / recovery_id / "job.json").read_text())
        command = recovery["runs"][0]["command"]
        self.assertIn("--resume-saved-campaign", command)
        self.assertEqual(command[command.index("--player-service-tier") + 1], "")
        self.assertEqual(command[command.index("--optimizer-service-tier") + 1], "")
        self.assertEqual(json.loads((source / "job.json").read_text())["resumed_as"], recovery_id)

    def test_inactive_resumable_batch_can_be_removed_from_runs_without_deleting_artifacts(self):
        source = self.root / "output/workbench/owned"
        self.put("output/workbench/owned/run-0001/campaign/evolution_config.json", {"max_evaluations": 2})
        row = {"id": "output/workbench/owned/run-0001/campaign", "output": str(source / "run-0001"),
               "status": "failed"}
        self.put("output/workbench/owned/job.json", {
            "status": "failed", "config": {"kind": "avo"}, "runs": [row],
        })
        with self.client() as client:
            response = client.post("/api/workbench/experiments/dismiss", params={"job": "output/workbench/owned"})
            self.assertEqual(response.status_code, 200)
            catalog = client.get("/api/workbench/catalog").json()
        manifest = json.loads((source / "job.json").read_text())
        self.assertTrue(manifest["dismissed_from_runs_at"])
        self.assertTrue((source / "run-0001/campaign/evolution_config.json").is_file())
        job = catalog["jobs"][0]
        self.assertTrue(job["can_resume"])
        self.assertFalse(job["can_dismiss"])
        self.assertEqual(job["dismissed_from_runs_at"], manifest["dismissed_from_runs_at"])

    def test_active_batch_cannot_be_removed_from_runs(self):
        self.put("output/workbench/owned/job.json", {
            "status": "running", "config": {"kind": "avo"}, "runs": [],
        })
        with self.client() as client:
            response = client.post("/api/workbench/experiments/dismiss", params={"job": "output/workbench/owned"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("dismissed_from_runs_at", json.loads((self.root / "output/workbench/owned/job.json").read_text()))

    def test_failed_child_can_resume_while_sibling_runs_without_losing_source_trace(self):
        source = self.root / "output/workbench/owned"
        saved = {"profile_settings":{"game_id":"ps_knightoban-v1", "backend_url":"http://host.docker.internal:8000"},
                 "player":{"model":"openrouter/deepseek/deepseek-v4.1-flash", "effort":"max", "max_environment_steps":300},
                 "optimizer_model":"openrouter/deepseek/deepseek-v4.1-flash", "optimizer_effort":"max",
                 "max_evaluations":15, "fresh_solver_max_environment_steps":1500,
                 "max_wall_seconds":86400, "world_model_mode":"final-only"}
        self.put("output/workbench/owned/run-0002/campaign/evolution_config.json", saved)
        self.put("output/workbench/owned/run-0002/campaign/lineage.json", {
            "candidates":[{"candidate_id":"x_0001"}], "evaluations":[]})
        self.put("output/workbench/owned/run-0002/campaign/x_0001/manifest.json", {"candidate_id":"x_0001"})
        strategy = source / "run-0002/campaign/x_0001/STRATEGY.md"
        strategy.write_text("Saved hypothesis", encoding="utf-8")
        self.put("output/workbench/owned/run-0002/campaign/x_0001/research/partial.json", {})
        self.put("output/workbench/owned/run-0002/campaign/optimizer_analysis/trace.json", {"original":"kept"})
        run_id = "output/workbench/owned/run-0002/campaign"
        rows = [{"id":"output/workbench/owned/run-0001/campaign", "status":"running", "game_id":"ps_modality-v1"},
                {"id":run_id, "output":str(source / "run-0002"), "status":"failed", "kind":"avo",
                 "game_id":"ps_knightoban-v1", "model":saved["player"]["model"], "effort":"max"}]
        self.put("output/workbench/owned/job.json", {"status":"running", "config":{"kind":"avo", "parallel":2,
                 "trace_detail":"full", "max_hours":24}, "runs":rows})
        with self.client() as client, patch("workbench.experiments.subprocess.Popen") as popen:
            response = client.post("/api/workbench/experiments/resume-run", params={"run":run_id}, json={})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(client.post("/api/workbench/experiments/resume-run", params={"run":run_id}, json={}).status_code, 409)
        popen.assert_called_once()
        recovery = json.loads((self.root / response.json()["id"] / "job.json").read_text())
        target = self.root / response.json()["run"]
        self.assertEqual(recovery["recovery_of"], run_id)
        self.assertEqual(len(recovery["runs"]), 1)
        self.assertIn("--resume-saved-campaign", recovery["runs"][0]["command"])
        self.assertEqual(recovery["config"]["parallel"], 1)
        self.assertEqual(recovery["config"]["trace_detail"], "full")
        self.assertEqual((target / "x_0001/STRATEGY.md").read_text(), "Saved hypothesis")
        self.assertFalse((target / "x_0001/research").exists())
        self.assertFalse((target / "optimizer_analysis").exists())
        self.assertTrue((source / "run-0002/campaign/x_0001/research/partial.json").exists())
        self.assertTrue((source / "run-0002/campaign/optimizer_analysis/trace.json").exists())
        self.assertEqual(json.loads((source / "job.json").read_text())["runs"][0]["status"], "running")
        self.assertEqual(json.loads((source / "run-0002/recovery.json").read_text())["resumed_as"], response.json()["run"])

    def test_recovery_rejects_unsafe_candidate_id_before_copy(self):
        source, target = self.root / "old", self.root / "new"
        self.put("old/campaign/evolution_config.json", {"max_evaluations":2})
        self.put("old/campaign/lineage.json", {"candidates":[{"candidate_id":"../../outside"}], "evaluations":[]})
        with self.assertRaises(ValueError):
            prepare_avo_recovery(source, target)
        self.assertFalse(target.exists())

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

    def test_pause_stops_children_and_marks_saved_work_resumable(self):
        directory = self.root / "output/workbench/job"
        directory.mkdir(parents=True)
        write_json(directory / "job.json", {"config":{"kind":"avo", "parallel":1, "max_hours":.1}, "runs":[{"kind":"avo", "status":"queued"}]})
        (directory / "pause.request").touch()
        with patch("workbench.experiment_job.subprocess.Popen") as popen:
            run_job(directory)
            popen.assert_not_called()
        data = json.loads((directory / "job.json").read_text())
        self.assertEqual(data["status"], "paused")
        self.assertEqual(data["runs"][0]["status"], "paused")

    def test_recovery_copy_discards_only_interrupted_runtime_evidence(self):
        source, target = self.root / "old", self.root / "new"
        campaign = source / "campaign"
        self.put("old/campaign/evolution_config.json", {"max_evaluations":2})
        self.put("old/campaign/lineage.json", {"candidates":[{"candidate_id":"x_0001"},{"candidate_id":"x_0002"}], "evaluations":[{"candidate_id":"x_0001"}]})
        self.put("old/campaign/x_0001/research/kept.json", {})
        self.put("old/campaign/x_0002/manifest.json", {})
        self.put("old/campaign/x_0002/seed/NOTES.json", {})
        self.put("old/campaign/x_0002/research/partial.json", {})
        _, complete = prepare_avo_recovery(source, target)
        self.assertFalse(complete)
        self.assertTrue((target / "campaign/x_0001/research/kept.json").is_file())
        self.assertTrue((target / "campaign/x_0002/seed/NOTES.json").is_file())
        self.assertFalse((target / "campaign/x_0002/research").exists())

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
