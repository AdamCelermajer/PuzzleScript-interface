import base64
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.results import build_matrix, create_router

GAMES = {"ps_alpha-v1": {"title": "Alpha", "tier": "easy", "levels": 4},
         "ps_beta-v1": {"title": "Beta", "tier": "hard", "levels": 6}}


def evaluation(fitness, win_levels):
    return {"fitness": fitness, "score": {"environment_task": {"score": {"win_levels": win_levels}}}}


RUNS = [
    # New-format direct play: two attempts in one cell, the better one wins.
    {"id": "new/a1", "kind": "codex", "harness": "claude-code", "model": "claude-haiku-5-5", "mode": "baseline-plus",
     "game_id": "ps_alpha-v1", "spec_source": "run_spec", "has_result": True, "levels": 1, "recorded_win_levels": 4,
     "solved": False, "modified": 10},
    {"id": "new/a2", "kind": "codex", "harness": "claude-code", "model": "claude-haiku-5-5", "mode": "baseline-plus",
     "game_id": "ps_alpha-v1", "spec_source": "run_spec", "has_result": True, "levels": 3, "recorded_win_levels": 4,
     "solved": False, "modified": 5},
    # New-format campaign: levels from fresh fitness, total from the evaluation score.
    {"id": "new/c/campaign", "kind": "avo", "harness": "opencode", "model": "openrouter/qwen/qwen3.8-27b",
     "mode": "campaign", "game_id": "ps_beta-v1", "spec_source": "run_spec", "has_result": True, "best_fitness": 6.0,
     "solved": True, "modified": 20, "result_inputs": {"evaluations": [evaluation(6.0, 6)]}},
    # Legacy run: archive only; falls back to games.json for the total.
    {"id": "old/x", "kind": "codex", "agent_backend": "codex", "harness": "codex", "model": "gpt-5.5", "mode": "baseline",
     "game_id": "ps_alpha-v1", "spec_source": "legacy", "has_result": True, "levels": 2, "solved": False, "modified": 1},
    # Queued child without artifacts: never counted.
    {"id": "queued", "kind": "codex", "harness": "codex", "model": "gpt-5.5", "game_id": "ps_beta-v1", "status": "queued"},
]


class MatrixTests(unittest.TestCase):
    def test_new_runs_only_by_default(self):
        matrix = build_matrix(RUNS, GAMES)
        self.assertEqual([g["game_id"] for g in matrix["games"]], ["ps_alpha-v1", "ps_beta-v1"])
        self.assertEqual([(c["harness"], c["label"]) for c in matrix["columns"]],
                         [("claude-code", "claude-haiku-5-5"), ("opencode", "qwen3.8-27b")])
        cell = matrix["cells"]["ps_alpha-v1|claude-code|claude-haiku-5-5"]
        self.assertEqual((cell["best_levels"], cell["win_levels"], cell["runs"], cell["best_run_id"], cell["solved"]),
                         (3, 4, 2, "new/a2", False))
        self.assertEqual(cell["run_ids"], ["new/a1", "new/a2"])  # newest first
        campaign = matrix["cells"]["ps_beta-v1|opencode|openrouter/qwen/qwen3.8-27b"]
        self.assertEqual((campaign["best_levels"], campaign["win_levels"], campaign["solved"]), (6, 6, True))

    def test_archive_and_mode_filters(self):
        archive = build_matrix(RUNS, GAMES, archive=True)
        legacy = archive["cells"]["ps_alpha-v1|codex|gpt-5.5"]
        self.assertEqual((legacy["best_levels"], legacy["win_levels"], legacy["runs"]), (2, 4, 1))
        self.assertEqual(archive["columns"][0]["harness"], "codex")  # harness order, codex first
        campaigns = build_matrix(RUNS, GAMES, mode="campaign")
        self.assertEqual(list(campaigns["cells"]), ["ps_beta-v1|opencode|openrouter/qwen/qwen3.8-27b"])
        self.assertEqual([g["game_id"] for g in campaigns["games"]], ["ps_beta-v1"])

    def test_route(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "benchmark").mkdir()
            (root / "benchmark/games.json").write_text(json.dumps({"schema": "games-v1", "games": GAMES}), encoding="utf-8")
            app = FastAPI()
            app.include_router(create_router(root, run_snapshot=lambda: {"runs": RUNS, "checked_at": 7.0}))
            client = TestClient(app)
            body = client.get("/api/workbench/results/matrix").json()
            self.assertEqual((body["archive"], body["checked_at"], len(body["cells"])), (False, 7.0, 2))
            self.assertEqual(len(client.get("/api/workbench/results/matrix?archive=1").json()["cells"]), 3)
            self.assertEqual(client.get("/api/workbench/results/matrix?archive=2").status_code, 422)
            self.assertEqual(client.get("/api/workbench/results/matrix?mode=nope").status_code, 422)


PNG = b"\x89PNG\r\n\x1a\n" + b"fixture"


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        from tests.workbench.test_benchmarks import make_fixture
        from scripts import build_game_metadata as builder
        from workbench.benchmarks import create_router as benchmarks_router
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        builder.main(["--root", str(self.root)])
        self.calls = []
        self.png = PNG
        app = FastAPI()
        app.include_router(benchmarks_router(self.root, backend_post=self.backend, run_snapshot=lambda: {"runs": []}))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def backend(self, path, body):
        self.calls.append(path)
        if path == "/api/scorecard/open":
            return {"card_id": "card-1"}
        if path == "/api/scorecard/close":
            return {}
        data = base64.b64encode(self.png).decode() if self.png else ""
        return {"guid": "g", "rendered_frame": {"data_url": f"data:image/png;base64,{data}"} if self.png else None}

    def test_renders_once_then_serves_the_cache(self):
        url = "/api/workbench/benchmarks/ps_alpha-v1/thumbnail.png"
        first = self.client.get(url)
        self.assertEqual((first.status_code, first.content, first.headers["content-type"]), (200, PNG, "image/png"))
        self.assertIn("max-age", first.headers["cache-control"])
        self.assertEqual(self.calls, ["/api/scorecard/open", "/api/cmd/RESET", "/api/scorecard/close"])
        self.assertEqual((self.root / "output/thumbnails/ps_alpha-v1.png").read_bytes(), PNG)
        self.assertEqual(self.client.get(url).content, PNG)
        self.assertEqual(len(self.calls), 3)  # served from output/thumbnails

    def test_missing_render_is_404_and_not_retried_at_once(self):
        self.png = None
        url = "/api/workbench/benchmarks/ps_alpha-v1/thumbnail.png"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.calls.count("/api/cmd/RESET"), 1)
        self.assertEqual(self.client.get("/api/workbench/benchmarks/ps_nope-v1/thumbnail.png").status_code, 404)


if __name__ == "__main__":
    unittest.main()
