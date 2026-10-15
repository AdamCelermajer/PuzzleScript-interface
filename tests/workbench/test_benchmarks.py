import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts import build_game_metadata as builder
from scripts import draft_game_tags as drafter
from workbench.benchmarks import create_router, measured_by_game

SECRET = "SECRET_RULE_TEXT"


def script(symbols: int) -> str:
    legend = "\n".join(f"{chr(97 + i)} = Wall" for i in range(symbols))
    return f"title Fixture\n\nOBJECTS\n\nLEGEND\n\n{legend}\n\nCOLLISIONLAYERS\n\nRULES\n\n[ > Player | {SECRET} ] -> []\n"


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


def make_fixture(root: Path) -> None:
    games = root / "puzzlescript_interface/games"
    write(games / "ps_alpha-v1/script.txt", script(3))
    write(games / "ps_alpha-v1/readme.txt", "Alpha readme")
    write(games / "ps_beta-v1/script.txt", script(3))
    write(games / "ps_wide-v1/script.txt", script(20))  # above MAX_VISIBLE_SYMBOLS
    (games / "ps_empty-v1").mkdir(parents=True)
    audit = [
        {"game_id": "ps_alpha-v1", "status": "parsed", "title": "Alpha", "author": "A", "homepage": "a.org",
         "exclusion_reasons": [], "object_count": 5, "parsed_rule_groups": 3, "map_levels": 14, "max_area": 400,
         "features": {"action_button": True}, "runtime_smoke_passed": True},
        {"game_id": "ps_beta-v1", "status": "parsed", "title": "Beta", "exclusion_reasons": ["random_rules"],
         "object_count": 2, "parsed_rule_groups": 1, "map_levels": 2, "max_area": 20, "features": {},
         "runtime_smoke_passed": None},
        {"game_id": "ps_wide-v1", "status": "parsed", "title": "Wide", "exclusion_reasons": [], "map_levels": 1,
         "max_area": 10, "features": {}, "runtime_smoke_passed": True},
        {"game_id": "ps_empty-v1", "status": "no_script", "runtime_smoke_passed": None},
    ]
    write(root / "benchmark/vetting/catalog-audit.json", {"games": audit})
    write(root / "benchmark/vetting/selection-v0.json", {"selection": [
        {"game_id": "ps_alpha-v1", "tier": "medium", "mechanic_summary": "Old summary."},
        {"game_id": "ps_beta-v1", "tier": "hard", "mechanic_summary": "Beta summary."}]})
    write(root / "output/game-selection-20/selection.json", {"games": [
        {"id": "ps_alpha-v1", "name": "Alpha!", "difficulty": "Easy", "rules": ["1. Push things.", "2. Win."]}]})
    write(root / "output/game-selection-20/level-inventory.json", [{"id": "ps_alpha-v1", "maps": [{}] * 12}])
    write(root / "benchmark/games/index.json", {"games": [{"game_id": "ps_beta-v1"}]})
    write(root / "benchmark/games/ps_beta-v1/game.json", {"artifact_status": "replay_verified", "level_artifacts": [
        {"level_index": 0, "solution_actions": 9, "replay_verified": True}]})
    write(root / "experiement/bfs_solver/semantic_all_60s_results.json", {"generatedAt": "x", "results": [
        {"gameId": "ps_beta-v1", "levelIndex": 2, "solved": False, "status": "time_limit", "solutionDepth": None},
        {"gameId": "ps_beta-v1", "levelIndex": 1, "solved": True, "status": "solved", "solutionDepth": 11}]})
    write(root / "experiement/bfs_solver/results.json", {"results": [
        {"gameId": "ps_beta-v1", "levelIndex": 0, "solved": False, "status": "time_limit"}]})


RUNS = {"checked_at": 1.0, "warnings": [], "runs": [
    {"id": "a", "kind": "codex", "agent_backend": "codex", "game_id": "ps_alpha-v1", "has_result": True,
     "solved": True, "levels": 12},
    {"id": "b", "kind": "avo", "harness": "claude-code", "game_id": "ps_alpha-v1", "has_result": False,
     "solved": False, "best_fitness": 3.0},
    {"id": "queued", "game_id": "ps_alpha-v1", "solved": False},
]}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_merges_sources(self):
        data = builder.build(self.root)
        self.assertEqual(data["schema"], "games-v1")
        games = data["games"]
        self.assertEqual(set(games), {"ps_alpha-v1", "ps_beta-v1", "ps_wide-v1", "ps_empty-v1"})
        alpha, beta = games["ps_alpha-v1"], games["ps_beta-v1"]
        self.assertEqual((alpha["tier"], alpha["tier_source"]), ("easy", "selection-20"))
        self.assertEqual((beta["tier"], beta["tier_source"]), ("hard", "selection-v0"))
        self.assertIsNone(games["ps_wide-v1"]["tier_source"])
        self.assertEqual(alpha["title"], "Alpha!")
        self.assertEqual(alpha["levels"], 12)
        self.assertEqual(alpha["collections"], ["selection-20", "selection-v0"])
        self.assertEqual(beta["collections"], ["selection-v0", "reference"])
        self.assertEqual(alpha["status"], "playable")
        self.assertEqual((beta["status"], beta["exclusion_reasons"]), ("excluded", ["random_rules"]))
        self.assertEqual(games["ps_wide-v1"]["exclusion_reasons"], ["not_in_arc_catalog"])
        self.assertFalse(games["ps_wide-v1"]["arc_catalog"])
        self.assertEqual(games["ps_empty-v1"]["exclusion_reasons"], ["no_script"])
        self.assertEqual(beta["bfs"]["depth"], 11)
        self.assertEqual(beta["bfs"]["level"], 1)
        self.assertEqual(alpha["tags"]["properties"], ["action-button", "many-levels", "large-maps"])
        self.assertEqual(beta["tags"]["properties"], ["randomness"])
        self.assertEqual(alpha["tags_status"], "none")
        self.assertEqual((alpha["summary"], alpha["summary_source"]), ("Old summary.", "selection-v0"))
        self.assertIn("push", data["tag_vocabulary"]["mechanics"])
        self.assertTrue(all(data["tag_definitions"][t] for kind in data["tag_vocabulary"].values() for t in kind))

    def test_rebuild_is_idempotent_and_preserves_curation(self):
        builder.main(["--root", str(self.root)])
        path = self.root / builder.GAMES_JSON
        data = json.loads(path.read_text(encoding="utf-8"))
        alpha = data["games"]["ps_alpha-v1"]
        alpha.update(tier="hard", tier_source="manual", notes="keep me", tags_status="draft",
                     summary="Drafted.", summary_source="draft",
                     tags={"mechanics": ["push"], "properties": ["hidden-state", "realtime"]})
        data["games"]["ps_beta-v1"].update(tags={"mechanics": ["slide"], "properties": []}, tags_status="reviewed")
        path.write_text(json.dumps(data), encoding="utf-8")
        builder.main(["--root", str(self.root)])
        rebuilt = json.loads(path.read_text(encoding="utf-8"))
        alpha = rebuilt["games"]["ps_alpha-v1"]
        self.assertEqual((alpha["tier"], alpha["tier_source"], alpha["notes"]), ("hard", "manual", "keep me"))
        self.assertEqual((alpha["summary"], alpha["tags_status"]), ("Drafted.", "draft"))
        # Derived properties are re-derived from the audit; drafted ones stay.
        self.assertEqual(alpha["tags"], {"mechanics": ["push"],
                                         "properties": ["hidden-state", "action-button", "many-levels", "large-maps"]})
        self.assertEqual(rebuilt["games"]["ps_beta-v1"]["tags"], {"mechanics": ["slide"], "properties": []})
        self.assertEqual(builder.main(["--root", str(self.root), "--check"]), 0)

    def test_draft_writes_drafts_and_skips_reviewed(self):
        builder.main(["--root", str(self.root)])
        path = self.root / builder.GAMES_JSON
        data = json.loads(path.read_text(encoding="utf-8"))
        data["games"]["ps_beta-v1"]["tags_status"] = "reviewed"
        path.write_text(json.dumps(data), encoding="utf-8")
        calls = []

        def fake(game_id, entry, text, token, timeout):
            calls.append(game_id)
            self.assertIn(SECRET, text)
            return {"mechanics": ["push"], "properties": ["irreversible"], "summary": f"{game_id} summary"}

        with mock.patch.object(drafter, "draft_one", fake), mock.patch.object(drafter, "env_token", lambda root: "t"):
            self.assertEqual(drafter.main(["--root", str(self.root)]), 0)
            self.assertEqual(sorted(calls), ["ps_alpha-v1", "ps_wide-v1"])
            calls.clear()
            self.assertEqual(drafter.main(["--root", str(self.root)]), 0)  # resumable: nothing left
            self.assertEqual(calls, [])
        games = json.loads(path.read_text(encoding="utf-8"))["games"]
        alpha = games["ps_alpha-v1"]
        self.assertEqual(alpha["tags_status"], "draft")
        self.assertEqual(alpha["tags"]["properties"], ["irreversible", "action-button", "many-levels", "large-maps"])
        self.assertEqual(alpha["summary"], "Old summary.")  # curated summary kept
        self.assertEqual(games["ps_wide-v1"]["summary"], "ps_wide-v1 summary")
        self.assertEqual(games["ps_beta-v1"]["tags_status"], "reviewed")

    def test_prompt_contains_vocabulary_but_not_derived_properties(self):
        text = drafter.prompt("ps_alpha-v1", {"title": "Alpha", "levels": 3}, "SCRIPT BODY")
        self.assertIn("- slide:", text)
        self.assertIn("SCRIPT BODY", text)
        self.assertNotIn("- realtime:", text)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        builder.main(["--root", str(self.root)])
        self.calls = []
        self.client = self.make_client()

    def tearDown(self):
        self.temp.cleanup()

    def backend(self, path, body):
        self.calls.append((path, body))
        if path == "/api/scorecard/open":
            return {"card_id": "card-1"}
        if path == "/api/scorecard/close":
            return {"card_id": body["card_id"]}
        return {"game_id": body["game_id"], "guid": "guid-1", "frame": [[[0, 1], [1, 0]]], "state": "NOT_FINISHED",
                "levels_completed": 0, "win_levels": 12, "available_actions": [1, 2, 3, 4, 7],
                "action_input": {"id": 0, "data": {}}, "rendered_frame": {"data_url": "data:image/png;base64,"},
                "projection": {"mode": "visible-cell-v1", "patterns": {}}}

    def make_client(self):
        app = FastAPI()
        app.include_router(create_router(self.root, backend_post=self.backend, run_snapshot=lambda: RUNS))
        return TestClient(app)

    def test_measured_aggregation(self):
        measured = measured_by_game(RUNS["runs"])["ps_alpha-v1"]
        self.assertEqual((measured["runs"], measured["solved_runs"], measured["best_levels"]), (2, 1, 12))
        self.assertEqual(measured["by_harness"]["claude-code"], {"runs": 1, "solved_runs": 0, "best_levels": 3})

    def test_list_filters(self):
        url = "/api/workbench/benchmarks"
        body = self.client.get(url).json()
        self.assertEqual(body["count"], 4)
        alpha = next(g for g in body["games"] if g["game_id"] == "ps_alpha-v1")
        self.assertEqual(alpha["measured"]["solved_runs"], 1)
        self.assertEqual(next(g for g in body["games"] if g["game_id"] == "ps_beta-v1")["measured"]["runs"], 0)
        ids = lambda **params: [g["game_id"] for g in self.client.get(url, params=params).json()["games"]]
        self.assertEqual(ids(tier="easy"), ["ps_alpha-v1"])
        self.assertEqual(ids(tier="none"), ["ps_empty-v1", "ps_wide-v1"])
        self.assertEqual(ids(collection="reference"), ["ps_beta-v1"])
        self.assertEqual(ids(status="excluded"), ["ps_beta-v1", "ps_empty-v1", "ps_wide-v1"])
        self.assertEqual(ids(tag="randomness"), ["ps_beta-v1"])
        self.assertEqual(ids(q="old summ"), ["ps_alpha-v1"])

    def test_detail_never_exposes_script_source(self):
        response = self.client.get("/api/workbench/benchmarks/ps_alpha-v1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SECRET, response.text)
        body = response.json()
        self.assertEqual(body["readme"], "Alpha readme")
        self.assertEqual(body["reviewed_rules"], ["1. Push things.", "2. Win."])
        self.assertEqual([r["id"] for r in body["runs"]], ["a", "b"])
        beta = self.client.get("/api/workbench/benchmarks/ps_beta-v1").json()
        self.assertEqual(beta["reference"]["levels"][0]["solution_actions"], 9)
        self.assertEqual(len(beta["bfs_searches"]), 3)
        self.assertEqual(self.client.get("/api/workbench/benchmarks/ps_nope-v1").status_code, 404)
        self.assertEqual(self.client.get("/api/workbench/benchmarks/..%2Fx").status_code, 404)

    def test_patch_validates_and_marks_curation(self):
        url = "/api/workbench/benchmarks/ps_wide-v1"
        bad = self.client.patch(url, json={"tags": {"mechanics": ["teleportation"], "properties": []}})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.client.patch(url, json={"tier": "extreme"}).status_code, 422)
        self.assertEqual(self.client.patch(url, json={}).status_code, 400)
        response = self.client.patch(url, json={"tier": "medium", "notes": " note ", "summary": "A  game.",
                                                "tags": {"mechanics": ["slide", "push"], "properties": []}})
        self.assertEqual(response.status_code, 200, response.text)
        saved = json.loads((self.root / builder.GAMES_JSON).read_text(encoding="utf-8"))["games"]["ps_wide-v1"]
        self.assertEqual((saved["tier"], saved["tier_source"]), ("medium", "manual"))
        self.assertEqual((saved["tags"]["mechanics"], saved["tags_status"]), (["push", "slide"], "reviewed"))
        self.assertEqual((saved["notes"], saved["summary"], saved["summary_source"]), ("note", "A game.", "manual"))
        builder.main(["--root", str(self.root)])
        rebuilt = json.loads((self.root / builder.GAMES_JSON).read_text(encoding="utf-8"))["games"]["ps_wide-v1"]
        self.assertEqual({k: rebuilt[k] for k in saved}, saved)
        cleared = self.client.patch(url, json={"tier": None}).json()
        self.assertEqual((cleared["tier"], cleared["tier_source"]), (None, "manual"))

    def test_play_proxies_arc_service(self):
        start = self.client.post("/api/workbench/benchmarks/ps_alpha-v1/play", json={"level": 2})
        self.assertEqual(start.status_code, 200, start.text)
        session = start.json()["session"]
        self.assertEqual(start.json()["frame"], [[[0, 1], [1, 0]]])
        self.assertEqual(self.calls[1], ("/api/cmd/RESET", {"game_id": "ps_alpha-v1", "card_id": "card-1", "level_index": 2}))
        move = self.client.post(f"/api/workbench/benchmarks/play/{session}/action4")
        self.assertEqual(move.status_code, 200)
        self.assertEqual(self.calls[-1], ("/api/cmd/ACTION4", {"game_id": "ps_alpha-v1", "guid": "guid-1"}))
        self.client.post(f"/api/workbench/benchmarks/play/{session}/RESET")
        self.assertEqual(self.calls[-1][1]["guid"], "guid-1")
        self.assertEqual(self.client.post(f"/api/workbench/benchmarks/play/{session}/ACTION6").status_code, 400)
        self.assertEqual(self.client.post("/api/workbench/benchmarks/play/nope/ACTION1").status_code, 404)
        self.assertEqual(self.client.post("/api/workbench/benchmarks/ps_wide-v1/play").status_code, 404)
        self.assertEqual(self.client.post("/api/workbench/benchmarks/ps_alpha-v1/play", json={"level": 99}).status_code, 400)
        self.assertEqual(self.client.delete(f"/api/workbench/benchmarks/play/{session}").json(), {"closed": True})
        self.assertEqual(self.calls[-1], ("/api/scorecard/close", {"card_id": "card-1"}))

    def test_reviewed_rule_edit(self):
        url = "/api/workbench/benchmarks/ps_alpha-v1/rules"
        conflict = self.client.put(url, json={"index": 0, "before": "stale", "value": "x"})
        self.assertEqual(conflict.status_code, 409)
        saved = self.client.put(url, json={"index": 0, "before": "1. Push things.", "value": "Push crates."})
        self.assertEqual(saved.json()["saved"], "1. Push crates.")
        selection = json.loads((self.root / "output/game-selection-20/selection.json").read_text(encoding="utf-8"))
        self.assertEqual(selection["games"][0]["rules"][0], "1. Push crates.")
        self.assertEqual(self.client.put("/api/workbench/benchmarks/ps_beta-v1/rules",
                                         json={"index": 0, "before": "", "value": "x"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
