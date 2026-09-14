import json
import tempfile
import unittest
from pathlib import Path

from studies.codex_agent.note_server import NoteWorkspace


class NoteWorkspaceTests(unittest.TestCase):
    def test_write_read_and_list_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir, "workspace")
            history = Path(tmpdir, "note_history")
            workspace = NoteWorkspace(root, history)

            written = workspace.call(
                "write_note",
                {"path": "strategy.md", "content": "Try moving right."},
            )
            replaced = workspace.call(
                "write_note",
                {"path": "strategy.md", "content": "Now move left."},
            )
            read = workspace.call("read_note", {"path": "strategy.md"})
            listed = workspace.call("list_notes", {})

            self.assertEqual(written["characters"], 17)
            self.assertNotIn("version", written)
            self.assertNotIn("history_path", written)
            self.assertNotIn("version", replaced)
            self.assertNotIn("history_path", replaced)
            self.assertEqual(read["content"], "Now move left.")
            self.assertEqual(listed["files"], ["strategy.md"])
            self.assertEqual(
                len(Path(root, "tool_calls.jsonl").read_text().splitlines()),
                4,
            )
            self.assertEqual(
                Path(history, "strategy.md.versions", "000001.md").read_text(),
                "Try moving right.",
            )
            self.assertEqual(
                Path(history, "strategy.md.versions", "000002.md").read_text(),
                "Now move left.",
            )
            audit = [
                json.loads(line)
                for line in Path(root, "tool_calls.jsonl").read_text().splitlines()
            ]
            self.assertEqual(audit[0]["version"], 1)
            self.assertEqual(
                audit[0]["history_path"],
                "strategy.md.versions/000001.md",
            )
            self.assertEqual(audit[1]["version"], 2)
            transitions = [
                json.loads(line)
                for line in Path(history, "note_transitions.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(len(transitions), 2)
            self.assertIsNone(transitions[0]["before_content"])
            self.assertEqual(transitions[0]["after_content"], "Try moving right.")
            self.assertEqual(transitions[1]["before_content"], "Try moving right.")
            self.assertEqual(transitions[1]["after_content"], "Now move left.")
            self.assertIn("-Try moving right.", transitions[1]["unified_diff"])
            self.assertIn("+Now move left.", transitions[1]["unified_diff"])

    def test_rejects_paths_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = NoteWorkspace(
                Path(tmpdir, "workspace"),
                Path(tmpdir, "note_history"),
            )

            with self.assertRaises(ValueError):
                workspace.call(
                    "write_note",
                    {"path": "../outside.md", "content": "no"},
                )

    def test_history_cannot_be_inside_model_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir, "workspace")
            with self.assertRaises(ValueError):
                NoteWorkspace(root, root / ".history")


if __name__ == "__main__":
    unittest.main()
