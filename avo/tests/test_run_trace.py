import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from avo.analysis.run_trace import RunTraceRecorder


@dataclass
class FakeEvent:
    method: str
    payload: object


class RunTraceRecorderTests(unittest.TestCase):
    def test_records_events_and_reconstructable_workspace_changes_outside_workspace(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            analysis = Path(root) / "run" / "analysis"
            workspace.mkdir()
            (workspace / "NOTES.md").write_text("first", encoding="utf-8")
            recorder = RunTraceRecorder(analysis, workspace)

            recorder.snapshot("initialized")
            (workspace / "NOTES.md").write_text("second", encoding="utf-8")
            recorder.record_event(
                FakeEvent("item/completed", {"item": {"type": "commandExecution"}}),
                1,
            )

            changes = [json.loads(line) for line in recorder.changes_path.read_text().splitlines()]
            self.assertIn("NOTES.md", changes[0]["added"])
            self.assertIn("NOTES.md", changes[1]["modified"])
            digest = changes[1]["modified"]["NOTES.md"]["sha256"]
            self.assertEqual((recorder.blob_root / digest).read_text(), "second")
            self.assertFalse((workspace / "analysis").exists())

    def test_does_not_record_reasoning_content_or_noisy_deltas(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            recorder = RunTraceRecorder(Path(root) / "analysis", workspace)
            recorder.record_event(
                FakeEvent(
                    "item/completed",
                    {"item": {"id": "r1", "type": "reasoning", "content": ["private"]}},
                ),
                1,
            )
            recorder.record_event(FakeEvent("item/agentMessage/delta", {"delta": "x"}), 1)

            events = [json.loads(line) for line in recorder.events_path.read_text().splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["payload"]["item"]["content"], "[not recorded]")
            self.assertNotIn("private", recorder.events_path.read_text())

    def test_locked_workspace_file_cannot_interrupt_the_run(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            locked = workspace / "locked.py"
            locked.write_text("running", encoding="utf-8")
            recorder = RunTraceRecorder(Path(root) / "analysis", workspace)
            original_read_bytes = Path.read_bytes

            def read_bytes(path):
                if path == locked:
                    raise PermissionError("temporarily locked")
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", read_bytes):
                recorder.snapshot("command_completed")

            change = json.loads(recorder.changes_path.read_text().splitlines()[0])
            self.assertEqual(change["errors"][0]["path"], "locked.py")
            self.assertIn("PermissionError", change["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
