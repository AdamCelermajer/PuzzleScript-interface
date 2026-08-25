import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avo.legacy.run_avo_agent import _archive_workspace
from avo.legacy.session import AvoCodexSession, AvoSessionConfig


class FakeResult:
    def __init__(self, payload: dict) -> None:
        self.final_response = json.dumps(payload)


class FakeThread:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = []

    def run(self, inputs, **kwargs):
        self.calls.append({"inputs": inputs, **kwargs})
        return FakeResult(self.payload)


class FakeCodex:
    instances = []

    def __init__(self, config=None) -> None:
        self.config = config
        self.thread_calls = []
        self.threads = [
            FakeThread(
                {
                    "actions": ["ACTION4"],
                    "prediction": "move right",
                    "note": "probe",
                    "confidence": "low",
                }
            ),
            FakeThread({"diagnosis": "stuck", "advice": "change direction"}),
        ]
        FakeCodex.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def thread_start(self, **kwargs):
        self.thread_calls.append(kwargs)
        return self.threads[len(self.thread_calls) - 1]


class AvoSessionTests(unittest.TestCase):
    def test_main_agent_is_workspace_write_and_supervisor_is_read_only(self) -> None:
        FakeCodex.instances.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("openai_codex.Codex", FakeCodex), patch(
                "avo.legacy.session._find_codex_bin", return_value="codex"
            ):
                with AvoCodexSession(
                    AvoSessionConfig(), Path(tmpdir) / "workspace"
                ) as session:
                    plan = session.next_plan("play")
                    review = session.supervise("review")

        self.assertEqual(plan["actions"], ["ACTION4"])
        self.assertEqual(review["advice"], "change direction")
        codex = FakeCodex.instances[0]
        self.assertEqual(codex.thread_calls[0]["sandbox"].value, "workspace-write")
        self.assertEqual(codex.thread_calls[1]["sandbox"].value, "read-only")
        self.assertTrue(codex.thread_calls[0]["ephemeral"])
        self.assertIn("Never\ninspect parent directories", codex.thread_calls[0]["base_instructions"])

    def test_workspace_archive_reports_sandbox_protected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            destination = Path(tmpdir) / "destination"
            source.mkdir()
            (source / "KNOWLEDGE.md").write_text("learned", encoding="utf-8")
            (source / "helper.py").write_text("print('solve')", encoding="utf-8")

            real_copy = __import__("shutil").copy2

            def selective_copy(path, target):
                if Path(path).name == "helper.py":
                    raise PermissionError("sandbox ACL")
                return real_copy(path, target)

            with patch("avo.legacy.run_avo_agent.shutil.copy2", side_effect=selective_copy):
                report = _archive_workspace(source, destination)

            self.assertEqual(report["copied"], ["KNOWLEDGE.md"])
            self.assertEqual(len(report["skipped"]), 1)
            self.assertIn("helper.py", report["skipped"][0])
            self.assertTrue((destination / "KNOWLEDGE.md").exists())


if __name__ == "__main__":
    unittest.main()
