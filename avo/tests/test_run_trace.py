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
    def test_compact_trace_preserves_conversation_without_raw_events_or_snapshots(self):
        with tempfile.TemporaryDirectory() as root, patch.dict("os.environ", {"AVO_TRACE_DETAIL": "compact"}):
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            (workspace / "large-data.json").write_text("x" * 1_000_000)
            recorder = RunTraceRecorder(Path(root) / "analysis", workspace)
            recorder.record_event(FakeEvent("item/completed", {"item": {"type": "agentMessage", "text": "learned rule"}}), 1)
            recorder.snapshot("finished")
            self.assertIn("learned rule", recorder.conversation_path.read_text())
            self.assertFalse(recorder.raw_events_path.exists())
            self.assertFalse(recorder.events_path.exists())
            self.assertEqual(list(recorder.blob_root.iterdir()), [])

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

    def test_keeps_raw_reasoning_and_deltas_but_preserves_compact_redaction(self):
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
            raw = [
                json.loads(line)
                for line in recorder.raw_events_path.read_text().splitlines()
            ]
            self.assertEqual(len(raw), 2)
            self.assertEqual(raw[0]["payload"]["item"]["content"], ["private"])
            self.assertEqual(raw[1]["payload"]["delta"], "x")
            conversation = json.loads(recorder.conversation_path.read_text().strip())
            self.assertEqual(conversation["role"], "assistant_reasoning")
            self.assertEqual(conversation["item"]["content"], ["private"])

    def test_records_session_prompt_turn_input_and_transport_status(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            recorder = RunTraceRecorder(Path(root) / "analysis", workspace)
            recorder.start_session(
                role="outer_optimizer",
                model="test-model",
                effort="high",
                codex_bin="patched-codex",
                base_instructions="system prompt",
                ephemeral=True,
                metadata={"candidate": "x_0001"},
            )
            recorder.attach_thread("thread-1")
            recorder.record_turn_input(
                turn_number=1,
                turn_id="turn-1",
                instruction="continue",
                effort="high",
            )
            recorder.transport_root.mkdir()
            (recorder.transport_root / "request-000001.json").write_text(
                "{}", encoding="utf-8"
            )
            recorder.finish_session(status="completed")

            session = json.loads(recorder.session_path.read_text())
            prompt = json.loads(recorder.prompt_path.read_text())
            turn = json.loads(recorder.turn_inputs_path.read_text().strip())
            conversation = json.loads(recorder.conversation_path.read_text().strip())
            self.assertEqual(session["role"], "outer_optimizer")
            self.assertEqual(session["thread_id"], "thread-1")
            self.assertEqual(session["capture"]["model_request_files"], 1)
            self.assertEqual(session["capture"]["model_request_status"], "captured")
            self.assertEqual(session["artifacts"]["model_requests"], "model_requests")
            self.assertEqual(prompt["base_instructions"], "system prompt")
            self.assertEqual(turn["inputs"][0]["text"], "continue")
            self.assertEqual(conversation["role"], "user")

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
