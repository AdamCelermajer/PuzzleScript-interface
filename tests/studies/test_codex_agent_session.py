import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from studies.codex_agent.session import CodexGameSession, CodexSessionConfig


class FakeThread:
    def __init__(self) -> None:
        self.calls = []

    def run(self, inputs, **kwargs):
        self.calls.append({"inputs": inputs, "kwargs": kwargs})
        return SimpleNamespace(
            id="turn-1",
            status="completed",
            error=None,
            started_at=1,
            completed_at=2,
            duration_ms=1000,
            final_response=json.dumps(
                {"action": "ACTION4", "note": "move right"}
            ),
            items=[{"type": "reasoning", "summary": ["Inspect the board"]}],
            usage={"totalTokens": 123},
        )


class FakeCodex:
    instances = []

    def __init__(self, config=None) -> None:
        self.config = config
        self.thread = FakeThread()
        self.thread_kwargs = None
        self.exited = False
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.exited = True

    def thread_start(self, **kwargs):
        self.thread_kwargs = kwargs
        return self.thread


class CodexSessionTests(unittest.TestCase):
    def setUp(self):
        self.proxy_patch = patch("avo.analysis.model_proxy.CodexRequestProxy")
        proxy_type = self.proxy_patch.start()
        self.addCleanup(self.proxy_patch.stop)
        proxy_type.return_value.model_base_url = "http://127.0.0.1:9"
        proxy_type.return_value.guard.failure = None
        proxy_type.return_value.guard.requests_checked = 1

    def test_uses_oauth_sdk_thread_with_sol_light_defaults(self) -> None:
        import openai_codex

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "frame.png").write_bytes(b"png")
            FakeCodex.instances.clear()
            with (
                patch.object(openai_codex, "Codex", FakeCodex),
                patch(
                    "studies.codex_agent.session._find_codex_bin",
                    return_value="C:/Codex/codex.exe",
                ),
            ):
                with CodexGameSession(
                    CodexSessionConfig(),
                    Path(tmpdir) / "workspace",
                    artifact_directory=tmpdir,
                ) as session:
                    response = session.next_action("frame", Path(tmpdir) / "frame.png")

            instance = FakeCodex.instances[-1]
            self.assertEqual(response["action"], "ACTION4")
            self.assertEqual(
                instance.config.codex_bin,
                "C:/Codex/codex.exe",
            )
            self.assertEqual(instance.thread_kwargs["model"], "gpt-5.6-sol")
            self.assertTrue(instance.thread_kwargs["ephemeral"])
            self.assertEqual(
                instance.thread.calls[0]["kwargs"]["effort"],
                "low",
            )
            self.assertTrue(instance.exited)
            self.assertEqual(
                Path(instance.thread.calls[0]["inputs"][1].path).name,
                "frame.png",
            )
            self.assertTrue(
                Path(instance.thread.calls[0]["inputs"][1].path).parent.name.startswith(
                    "codex-game-"
                )
            )
            session_log = [
                json.loads(line)
                for line in (Path(tmpdir) / "codex_session.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(session_log[0]["turn_kind"], "game_action")
            self.assertEqual(
                session_log[0]["turn"]["items"][0]["summary"],
                ["Inspect the board"],
            )

    def test_baseline_plus_configures_only_note_workspace(self) -> None:
        import openai_codex

        with tempfile.TemporaryDirectory() as tmpdir:
            FakeCodex.instances.clear()
            with (
                patch.object(openai_codex, "Codex", FakeCodex),
                patch(
                    "studies.codex_agent.session._find_codex_bin",
                    return_value="C:/Codex/codex.exe",
                ),
            ):
                with CodexGameSession(
                    CodexSessionConfig(workspace_enabled=True),
                    Path(tmpdir) / "workspace",
                    artifact_directory=tmpdir,
                ) as session:
                    instance = FakeCodex.instances[-1]
                    response = session.next_action("frame")

            self.assertEqual(response["operation"], "ACT")
            self.assertTrue(
                Path(instance.thread_kwargs["cwd"]).name.startswith("codex-game-")
            )
            self.assertNotEqual(
                Path(instance.thread_kwargs["cwd"]),
                Path(tmpdir) / "workspace",
            )
            self.assertEqual(
                instance.thread_kwargs["base_instructions"],
                "You are playing a puzzle game. Return exactly one next game action "
                "per turn. You have a persistent workspace with tools to list, read, "
                "and write notes. Use these tools as working memory. Before your first "
                "game action, write strategy.md with your initial observations, "
                "hypotheses, and plan. On later turns, read strategy.md before acting "
                "and update it whenever evidence confirms or rejects a hypothesis, "
                "your plan changes, you encounter a dead end, or a level changes. Keep "
                "confirmed facts separate from hypotheses. Tool calls happen before "
                "your final one-action response.",
            )
            self.assertEqual(
                instance.thread_kwargs["approval_mode"],
                openai_codex.ApprovalMode.deny_all,
            )
            overrides = instance.config.config_overrides
            self.assertTrue(
                any(item.startswith("mcp_servers.codex_notes.command=") for item in overrides)
            )
            self.assertIn(
                'mcp_servers.codex_notes.enabled_tools=["list_notes","read_note","write_note"]',
                overrides,
            )
            self.assertIn(
                'mcp_servers.codex_notes.default_tools_approval_mode="approve"',
                overrides,
            )
            self.assertIn("features.shell_tool=false", overrides)
            isolation = json.loads(
                Path(tmpdir, "isolation_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(isolation["initial_note_files"], [])
            self.assertEqual(
                isolation["model_visible_note_tools"],
                ["list_notes", "read_note", "write_note"],
            )


if __name__ == "__main__":
    unittest.main()
