import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench import board

CARD = """---
title: "What are Max, Flash and 27B good at?"
status: in-progress
order: 2
due: 2026-10-22
threads: [qwen-harness]
links:
  - "Audit | docs/research/audit.md"
  - "Paper | https://example.org/paper.pdf"
runs: [output/workbench/x/run-0001]
artifact: docs/research/scorecard.json
---
## Question
Which capabilities?

## Current answer
In progress.

## Evidence
- Max 4/4.

## Next
- Finish.
"""


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "docs/board").mkdir(parents=True)
        (self.root / "docs/research").mkdir(parents=True)
        (self.root / "docs/board/scorecard.md").write_text(CARD, encoding="utf-8")
        (self.root / "docs/board/broken.md").write_text("no front matter", encoding="utf-8")
        (self.root / "docs/research/audit.md").write_text("# Audit", encoding="utf-8")
        (self.root / "secret.md").write_text("outside docs", encoding="utf-8")
        patches = [mock.patch.object(board, "BOARD_DIR", self.root / "docs/board"),
                   mock.patch.object(board, "REPO_ROOT", self.root)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        app = FastAPI()
        app.include_router(board.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def test_list_parses_cards_and_reports_broken_files(self):
        body = self.client.get("/api/workbench/board").json()
        self.assertEqual([c["slug"] for c in body["cards"]], ["scorecard"])
        card = body["cards"][0]
        self.assertEqual((card["status"], card["order"], card["due"]), ("in-progress", 2, "2026-10-22"))
        self.assertEqual(card["links"], [{"label": "Audit", "path_or_url": "docs/research/audit.md"},
                                         {"label": "Paper", "path_or_url": "https://example.org/paper.pdf"}])
        self.assertEqual(card["sections"]["current_answer"], "In progress.")
        self.assertFalse(card["artifact_exists"])
        self.assertEqual([e["file"] for e in body["errors"]], ["broken.md"])

    def test_artifact_missing_then_present(self):
        self.assertEqual(self.client.get("/api/workbench/board/scorecard/artifact").status_code, 404)
        (self.root / "docs/research/scorecard.json").write_text(json.dumps({"models": ["Max"]}), encoding="utf-8")
        self.assertEqual(self.client.get("/api/workbench/board/scorecard/artifact").json(), {"models": ["Max"]})
        self.assertTrue(self.client.get("/api/workbench/board/scorecard").json()["artifact_exists"])

    def test_put_creates_and_round_trips(self):
        text = CARD.replace("order: 2", "order: 5").replace("in-progress", "todo")
        response = self.client.put("/api/workbench/board/new-card", json={"text": text})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["created"])
        saved = (self.root / "docs/board/new-card.md").read_text(encoding="utf-8")
        self.assertIn('  - "Audit | docs/research/audit.md"', saved)
        again = self.client.put("/api/workbench/board/new-card", json={"text": saved}).json()
        self.assertFalse(again["created"])
        self.assertEqual((again["card"]["status"], again["card"]["order"]), ("todo", 5))
        self.assertEqual(saved, (self.root / "docs/board/new-card.md").read_text(encoding="utf-8"))

    def test_put_validates(self):
        bad = {
            "status": CARD.replace("status: in-progress", "status: someday"),
            "sections": CARD.replace("## Evidence", "## Proof"),
            "path": CARD.replace("docs/research/audit.md", "../outside.md"),
            "artifact": CARD.replace("scorecard.json", "scorecard.txt"),
            "field": CARD.replace("order: 2", "order: 2\nowner: me"),
        }
        for name, text in bad.items():
            with self.subTest(name):
                self.assertEqual(self.client.put("/api/workbench/board/x", json={"text": text}).status_code, 422)
        self.assertEqual(self.client.put("/api/workbench/board/Bad_Slug", json={"text": CARD}).status_code, 400)
        self.assertFalse((self.root / "docs/board/x.md").exists())

    def test_patch_status_and_order(self):
        url = "/api/workbench/board/scorecard"
        response = self.client.patch(url, json={"status": "done", "order": 9})
        self.assertEqual((response.json()["status"], response.json()["order"]), ("done", 9))
        self.assertIn("status: done", (self.root / "docs/board/scorecard.md").read_text(encoding="utf-8"))
        self.assertEqual(self.client.patch(url, json={"status": "later"}).status_code, 422)
        self.assertEqual(self.client.patch(url, json={"title": "x"}).status_code, 422)
        self.assertEqual(self.client.patch("/api/workbench/board/missing", json={"status": "done"}).status_code, 404)

    def test_file_view_is_limited_to_docs(self):
        ok = self.client.get("/api/workbench/board/file", params={"path": "docs/research/audit.md"})
        self.assertEqual((ok.status_code, ok.text), (200, "# Audit"))
        self.assertEqual(self.client.get("/api/workbench/board/file", params={"path": "secret.md"}).status_code, 403)
        self.assertEqual(self.client.get("/api/workbench/board/file", params={"path": "docs/../secret.md"}).status_code, 400)
        self.assertEqual(self.client.get("/api/workbench/board/file", params={"path": "docs/research/none.md"}).status_code, 404)


class SeedCardsTests(unittest.TestCase):
    def test_repository_cards_are_valid(self):
        cards, errors = board.load_all()
        self.assertEqual(errors, [])
        self.assertEqual([c["slug"] for c in cards][:3], ["capability-scorecard", "capability-interventions", "flash-vs-max"])
        self.assertEqual(next(c for c in cards if c["slug"] == "proposal-presentation")["due"], "2026-10-22")


if __name__ == "__main__":
    unittest.main()
