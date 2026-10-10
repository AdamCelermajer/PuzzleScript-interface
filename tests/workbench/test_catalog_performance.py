"""The catalog carries result projections and serves pollers without blocking rebuilds."""
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench import experiments
from workbench.catalog import snapshot


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value, encoding="utf-8")


class CatalogPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_rows_carry_compact_result_inputs(self):
        avo = self.root / "output/a/campaign"
        write(avo / "evolution_config.json", {"player": {"effort": "high", "model": "m", "max_environment_steps": 9},
                                              "max_evaluations": 4, "profile_settings": {"game_id": "g"}})
        write(avo / "lineage.json", {"evaluations": [
            {"candidate_id": "x_1", "fitness": 2, "success": False, "environment_steps": 5, "workspace": "large",
             "score": {"environment_task": {"score": {"win_levels": 3}}, "search_session_elapsed_seconds": 7}},
            {"candidate_id": "x_2", "fitness": True}, {"candidate_id": "x_3"}]})
        codex = self.root / "output/b"
        write(codex / "run_config.json", {"condition": "baseline", "game_id": "g"})
        write(codex / "result.json", {"levels_completed": 1})
        write(codex / "transitions.jsonl", '{"after": {"win_levels": 6}}\n')
        rows = {row["id"]: row for row in snapshot(self.root, {})["runs"]}
        inputs = rows["output/a/campaign"]["result_inputs"]
        self.assertEqual([e["candidate_id"] for e in inputs["evaluations"]], ["x_1"])
        self.assertNotIn("workspace", inputs["evaluations"][0])
        self.assertEqual(inputs["evaluations"][0]["score"]["environment_task"]["score"]["win_levels"], 3)
        self.assertEqual(inputs["config"]["player"]["effort"], "high")
        self.assertFalse(inputs["finalized"])
        self.assertEqual(rows["output/b"]["recorded_win_levels"], 6)

    def test_catalog_serves_last_snapshot_while_one_rebuild_runs(self):
        calls = []

        def slow_snapshot(root):
            calls.append(time.monotonic())
            time.sleep(0.3)
            return {"runs": [{"n": len(calls)}], "jobs": [], "warnings": [], "checked_at": 0}

        app = FastAPI()
        app.include_router(experiments.create_router(self.root))
        with patch("workbench.experiments.snapshot", slow_snapshot), TestClient(app) as client:
            self.assertEqual(client.get("/api/workbench/catalog").json()["runs"], [{"n": 1}])
            with patch("workbench.experiments.time.monotonic", return_value=time.monotonic() + 10):
                started = time.monotonic()
                for _ in range(3):
                    self.assertEqual(client.get("/api/workbench/catalog").json()["runs"], [{"n": 1}])
                self.assertLess(time.monotonic() - started, 0.25)
            time.sleep(0.5)
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
