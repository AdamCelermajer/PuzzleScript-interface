"""Research diary API: parsing, validation, safe writes, run linking and export."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench import diary

README = """# Diary

## Threads

| Thread | Description | Status |
|---|---|---|
| `qwen-harness` | Why Qwen 27B fails | active |
| `proposal` | M.Sc proposal | active |
| `meetings` | Supervisor meetings | active |
"""

ENTRY = """---
date: 2026-10-14
title: "Qwen Max: verified 4/4"
threads: [qwen-harness]
runs: [output/workbench/explicit-run]
commits: [94086fe]
docs:
  - docs/research/qwen-modality-yoav-brief-20261014.md
reconstructed: false
---
## Did
- Audited the Modality runs.
  Replayed every saved action.
## Found
- Max solver 4/4 in 265 actions.
## Decided
- No causal claim about AVO.
## Next
- —
"""

BODY = "## Did\n- Wrote the proposal.\n## Found\n- —\n## Decided\n- Submit Sunday.\n## Next\n- Send to Yoav.\n"


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


class DiaryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.diary_dir = self.root / "docs/diary"
        write(self.diary_dir / "README.md", README)
        write(self.diary_dir / "2026-10-14-qwen-max-audit.md", ENTRY)
        # A dated direct run and an explicitly referenced run from another day.
        write(self.root / "output/workbench/20261014T101500-abc/run-0001/run_config.json",
              {"condition": "baseline-plus", "game_id": "ps_modality-v1", "model": "qwen/qwen3.8-max"})
        write(self.root / "output/workbench/20261014T101500-abc/run-0001/result.json",
              {"status": "completed", "levels_completed": 1, "win_levels": 4, "action_count": 100})
        write(self.root / "output/workbench/explicit-run/run_config.json",
              {"condition": "baseline", "game_id": "ps_icecrates-v1", "model": "m"})
        write(self.root / "output/workbench/explicit-run/run_spec.json",
              {"schema": "run-spec-v1", "mode": "baseline", "harness": "claude-code", "model": "claude-sonnet-5-5",
               "game_id": "ps_icecrates-v1", "created_at": "2026-10-10T09:00:00Z"})
        self.patches = [patch.object(diary, "DIARY_DIR", self.diary_dir), patch.object(diary, "RUN_ROOT", self.root)]
        for p in self.patches:
            p.start()
        diary._run_cache.clear()
        app = FastAPI()
        app.include_router(diary.router)
        self.client = TestClient(app)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        diary._run_cache.clear()
        self.temp.cleanup()

    def test_list_parses_front_matter_sections_and_links_runs(self):
        body = self.client.get("/api/workbench/diary").json()
        self.assertEqual(body["errors"], [])
        [entry] = body["entries"]
        self.assertEqual(entry["slug"], "2026-10-14-qwen-max-audit")
        self.assertEqual(entry["title"], "Qwen Max: verified 4/4")
        self.assertEqual(entry["threads"], ["qwen-harness"])
        self.assertEqual(entry["docs"], ["docs/research/qwen-modality-yoav-brief-20261014.md"])
        self.assertIs(entry["reconstructed"], False)
        self.assertIs(entry["brief"], False)
        self.assertIn("Replayed every saved action.", entry["sections"]["did"])
        self.assertEqual(entry["sections"]["next"], "- —")
        runs = {run["id"]: run for run in entry["runs"]}
        dated = runs["output/workbench/20261014T101500-abc/run-0001"]
        self.assertEqual((dated["linked"], dated["date"], dated["variant"], dated["game"]),
                         ("date", "2026-10-14", "Baseline", "ps_modality-v1"))
        self.assertIn("1/4 levels", dated["outcome"])
        explicit = runs["output/workbench/explicit-run"]
        self.assertEqual((explicit["linked"], explicit["harness"], explicit["date"]),
                         ("explicit", "claude-code", "2026-10-10"))

    def test_explicit_run_wildcard_and_missing_run(self):
        entry = ENTRY.replace("runs: [output/workbench/explicit-run]", "runs: [output/workbench/expl*, output/gone]")
        write(self.diary_dir / "2026-10-14-qwen-max-audit.md", entry)
        runs = self.client.get("/api/workbench/diary/2026-10-14-qwen-max-audit").json()["runs"]
        explicit = {r["id"]: r["found"] for r in runs if r["linked"] == "explicit"}
        self.assertEqual(explicit, {"output/workbench/explicit-run": True, "output/gone": False})

    def test_filters_by_thread_and_dates(self):
        get = lambda **q: self.client.get("/api/workbench/diary", params=q).json()["entries"]
        self.assertEqual(len(get(thread="qwen-harness")), 1)
        self.assertEqual(get(thread="proposal"), [])
        self.assertEqual(len(get(**{"from": "2026-10-14", "to": "2026-10-14"})), 1)
        self.assertEqual(get(**{"from": "2026-10-15"}), [])
        self.assertEqual(self.client.get("/api/workbench/diary", params={"from": "14/10"}).status_code, 400)

    def test_get_entry_and_missing_and_traversal(self):
        entry = self.client.get("/api/workbench/diary/2026-10-14-qwen-max-audit").json()
        self.assertTrue(entry["body"].startswith("## Did"))
        self.assertEqual(self.client.get("/api/workbench/diary/2026-10-13-nothing").status_code, 404)
        for slug in ("..%2F..%2Fsecret", "2026-10-14-..", "README", "2026-10-14-UPPER"):
            self.assertIn(self.client.get(f"/api/workbench/diary/{slug}").status_code, {400, 404})
            self.assertIn(self.client.put(f"/api/workbench/diary/{slug}", json={"text": ENTRY}).status_code, {400, 404, 405})

    def test_put_creates_validates_and_round_trips(self):
        payload = {"front_matter": {"date": "2026-10-16", "title": "Proposal: final pass", "threads": ["proposal"],
                                    "runs": [], "commits": [], "docs": ["docs/proposal/main.tex"],
                                    "reconstructed": False}, "body": BODY}
        response = self.client.put("/api/workbench/diary/2026-10-16-proposal-pass", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["created"])
        text = (self.diary_dir / "2026-10-16-proposal-pass.md").read_text(encoding="utf-8")
        self.assertIn('title: "Proposal: final pass"', text)
        self.assertEqual(list(self.diary_dir.glob(".diary-*")), [])
        again = self.client.put("/api/workbench/diary/2026-10-16-proposal-pass", json={"text": text})
        self.assertFalse(again.json()["created"])
        self.assertEqual((self.diary_dir / "2026-10-16-proposal-pass.md").read_text(encoding="utf-8"), text)
        self.assertEqual(again.json()["entry"]["sections"]["decided"], "- Submit Sunday.")
        brief = self.client.put("/api/workbench/diary/2026-10-16-proposal-pass",
                                json={"front_matter": {**payload["front_matter"], "brief": True}, "body": BODY})
        self.assertIs(brief.json()["entry"]["brief"], True)
        self.assertIn("brief: true\n---", (self.diary_dir / "2026-10-16-proposal-pass.md").read_text(encoding="utf-8"))

    def test_put_rejects_invalid_entries(self):
        base = {"date": "2026-10-16", "title": "t", "threads": ["proposal"], "reconstructed": False}
        cases = [
            ({**base, "date": "2026-10-17"}, BODY),                      # date differs from slug
            ({**base, "threads": []}, BODY),                             # no thread
            ({**base, "threads": ["Bad Thread"]}, BODY),
            ({**base, "commits": ["not-a-sha"]}, BODY),
            ({**base, "docs": ["../../etc/passwd"]}, BODY),
            ({**base, "docs": ["C:/Windows"]}, BODY),
            ({**base, "reconstructed": "yes"}, BODY),
            ({**base, "brief": "yes"}, BODY),
            ({**base, "extra": "x"}, BODY),
            (base, BODY.replace("## Found", "## Findings")),
            (base, "## Did\n- x\n## Next\n- y\n"),
        ]
        for meta, body in cases:
            response = self.client.put("/api/workbench/diary/2026-10-16-bad", json={"front_matter": meta, "body": body})
            self.assertEqual(response.status_code, 422, (meta, body))
        self.assertFalse((self.diary_dir / "2026-10-16-bad.md").exists())

    def test_unknown_thread_is_a_warning_and_threads_endpoint_counts(self):
        payload = {"front_matter": {"date": "2026-10-16", "title": "New", "threads": ["fresh-idea"]}, "body": BODY}
        response = self.client.put("/api/workbench/diary/2026-10-16-new", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["warnings"])
        threads = {t["id"]: t for t in self.client.get("/api/workbench/diary/threads").json()["threads"]}
        self.assertEqual(threads["qwen-harness"]["entries"], 1)
        self.assertEqual(threads["qwen-harness"]["status"], "active")
        self.assertEqual(threads["fresh-idea"]["status"], "unregistered")
        self.assertEqual(threads["proposal"]["entries"], 0)

    def test_invalid_file_is_reported_not_fatal(self):
        write(self.diary_dir / "2026-10-12-broken.md", "no front matter")
        body = self.client.get("/api/workbench/diary").json()
        self.assertEqual(len(body["entries"]), 1)
        self.assertEqual(body["errors"][0]["file"], "2026-10-12-broken.md")

    def test_export_markdown_and_html(self):
        md = self.client.get("/api/workbench/diary/export",
                             params={"from": "2026-10-01", "to": "2026-10-15", "format": "md"})
        self.assertEqual(md.status_code, 200)
        text = md.text
        self.assertIn("# Research progress, 2026-10-01 to 2026-10-15", text)
        self.assertIn("### qwen-harness (active)", text)
        self.assertIn("- (2026-10-14) Max solver 4/4 in 265 actions.", text)
        self.assertIn("- (2026-10-14) No causal claim about AVO.", text)
        self.assertIn("20261014T101500-abc", text)
        self.assertIn("`94086fe`", text)
        html = self.client.get("/api/workbench/diary/export",
                               params={"from": "2026-10-01", "to": "2026-10-15", "format": "html"})
        self.assertEqual(html.status_code, 200)
        self.assertIn("text/html", html.headers["content-type"])
        self.assertIn("@page { size: A4", html.text)
        self.assertIn("<h2>Key findings</h2>", html.text)
        self.assertIn("<table>", html.text)
        self.assertEqual(self.client.get("/api/workbench/diary/export", params={"format": "pdf"}).status_code, 400)

    def test_export_defaults_to_period_since_last_meeting(self):
        meeting = ENTRY.replace("2026-10-14", "2026-10-07").replace("[qwen-harness]", "[meetings]")
        write(self.diary_dir / "2026-10-07-meeting.md", meeting)
        text = self.client.get("/api/workbench/diary/export", params={"to": "2026-10-15"}).text
        self.assertIn("# Research progress, 2026-10-08 to 2026-10-15", text)
        self.assertIn("1 diary entry.", text)

    def test_html_escapes_entry_text(self):
        evil = ENTRY.replace("Audited the Modality runs.", "<script>alert(1)</script>")
        write(self.diary_dir / "2026-10-14-qwen-max-audit.md", evil)
        html = self.client.get("/api/workbench/diary/export",
                               params={"from": "2026-10-14", "to": "2026-10-14", "format": "html"}).text
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
