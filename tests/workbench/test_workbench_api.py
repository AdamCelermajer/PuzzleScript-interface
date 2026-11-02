import tempfile
import unittest
import shutil
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from workbench.app import create_app
from workbench.paper_library import PaperLibrary


def library(tmpdir):
    return PaperLibrary(Path(tmpdir) / ".paper-library")


class FakePaperAssistant:
    def __init__(self, answer="The claim survives only as an experimental treatment."):
        self.answer = answer
        self.calls = []

    def ask(self, **kwargs):
        self.calls.append(kwargs)
        return self.answer



class WorkbenchApiTests(unittest.TestCase):
    def test_paper_investigation_uses_grounded_assistant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assistant = FakePaperAssistant()
            client = TestClient(create_app(paper_assistant=assistant, paper_library=library(tmpdir)))
            response = client.post(
                "/api/workbench/paper-investigation/ask",
                json={
                    "paper": "vista",
                    "question": "Does this invalidate executable rules?",
                    "selected_passage": "Free-form language is sufficient.",
                    "history": [
                        {"role": "assistant", "content": "We should separate necessity from usefulness."}
                    ],
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["answer"], assistant.answer)
            self.assertEqual(assistant.calls[0]["paper"], "vista")
            self.assertEqual(
                assistant.calls[0]["selected_passage"],
                "Free-form language is sufficient.",
            )

    def test_paper_investigation_rejects_invalid_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(
                create_app(paper_assistant=FakePaperAssistant(), paper_library=library(tmpdir))
            )
            response = client.post(
                "/api/workbench/paper-investigation/ask",
                json={"paper": "unknown", "question": "Explain this."},
            )

            self.assertEqual(response.status_code, 404)

    @staticmethod
    def sample_pdf(title="A saved research paper"):
        stream = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.add_metadata({"/Title": title, "/Author": "Ada Researcher"})
        writer.write(stream)
        return stream.getvalue()

    def test_paper_library_upload_status_annotations_and_questions_are_folder_backed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assistant = FakePaperAssistant("Linked evidence changes the claim.")
            library = PaperLibrary(Path(tmpdir) / "papers")
            client = TestClient(create_app(
                paper_assistant=assistant, paper_library=library
            ))

            uploaded = client.post(
                "/api/workbench/paper-investigation/papers/upload",
                params={"filename": "experiment.pdf"},
                content=self.sample_pdf(),
                headers={"Content-Type": "application/pdf"},
            )
            self.assertEqual(uploaded.status_code, 201)
            paper = uploaded.json()["paper"]
            paper_id = paper["id"]
            paper_dir = Path(tmpdir) / "papers" / paper_id
            self.assertEqual(paper["title"], "A saved research paper")
            self.assertTrue((paper_dir / "paper.pdf").is_file())
            self.assertTrue((paper_dir / "text.txt").is_file())
            self.assertTrue((paper_dir / "annotations.json").is_file())
            self.assertTrue((paper_dir / "questions.json").is_file())

            status = client.patch(
                f"/api/workbench/paper-investigation/papers/{paper_id}",
                json={"status": "finished", "last_page": 1},
            )
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["paper"]["status"], "finished")
            self.assertTrue(status.json()["paper"]["completed_at"])

            added = client.post(
                f"/api/workbench/paper-investigation/papers/{paper_id}/annotations",
                json={
                    "id": "underline-1",
                    "quote": "The decisive passage.",
                    "page": 1,
                    "comment": "This changes the baseline.",
                },
            )
            self.assertEqual(added.status_code, 201)
            updated = client.patch(
                f"/api/workbench/paper-investigation/papers/{paper_id}/annotations/underline-1",
                json={"comment": "Compare against the same model."},
            )
            self.assertEqual(
                updated.json()["annotation"]["comment"],
                "Compare against the same model.",
            )

            asked = client.post(
                "/api/workbench/paper-investigation/ask",
                json={
                    "paper_ids": [paper_id],
                    "annotation_ids": ["underline-1"],
                    "question": "What does this change?",
                },
            )
            self.assertEqual(asked.status_code, 200)
            self.assertIn("The decisive passage", assistant.calls[0]["source_context"])
            saved = client.get(
                f"/api/workbench/paper-investigation/papers/{paper_id}"
            ).json()
            self.assertEqual(saved["paper"]["annotation_count"], 1)
            self.assertEqual(saved["paper"]["question_count"], 1)
            self.assertEqual(saved["questions"][0]["annotation_ids"], ["underline-1"])
            self.assertEqual(
                client.get(
                    f"/api/workbench/paper-investigation/papers/{paper_id}/pdf"
                ).status_code,
                200,
            )

    def test_paper_library_accepts_arxiv_links_and_keeps_stable_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            library = PaperLibrary(Path(tmpdir) / "papers")
            client = TestClient(create_app(paper_library=library))
            with patch.object(library, "_download_pdf", return_value=self.sample_pdf("Linked paper")):
                response = client.post(
                    "/api/workbench/paper-investigation/papers/import",
                    json={"url": "https://arxiv.org/abs/2603.99999"},
                )

            self.assertEqual(response.status_code, 201)
            paper = response.json()["paper"]
            self.assertEqual(paper["id"], "arxiv-2603-99999")
            self.assertEqual(paper["source_type"], "arxiv")
            self.assertTrue((Path(tmpdir) / "papers" / paper["id"] / "paper.pdf").is_file())

    def test_paper_question_can_link_multiple_selected_papers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assistant = FakePaperAssistant("The comparison needs a matched ablation.")
            library = PaperLibrary(Path(tmpdir) / "papers")
            client = TestClient(create_app(
                paper_assistant=assistant, paper_library=library
            ))

            response = client.post(
                "/api/workbench/paper-investigation/ask",
                json={
                    "paper_ids": ["avo", "vista"],
                    "question": "Where do these papers actually collide?",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["paper_ids"], ["avo", "vista"])
            self.assertEqual(assistant.calls[0]["paper"], "avo, vista")
            self.assertEqual(len(library.questions("avo")), 1)
            self.assertEqual(len(library.questions("vista")), 1)
            self.assertEqual(
                library.questions("avo")[0]["id"],
                library.questions("vista")[0]["id"],
            )

    def test_codex_status_endpoint_reports_desktop_oauth_state(self):
        status = {"available": True, "logged_in": True, "state": "ready", "version": "codex-cli test",
                  "message": "Logged in using ChatGPT"}
        with tempfile.TemporaryDirectory() as tmpdir, patch("workbench.app.codex_oauth_status", lambda: status):
            response = TestClient(create_app(paper_library=library(tmpdir))).get("/api/workbench/codex/status")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["logged_in"])
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_health_reports_ok(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            response = TestClient(create_app(paper_library=library(tmpdir))).get("/api/workbench/health")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["ok"])


if __name__ == "__main__":
    unittest.main()
