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
        self.proxy_type = proxy_type
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
            self.assertNotIn("output_schema", instance.thread.calls[0]["kwargs"])
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
            self.assertIn("read strategy.md before acting", instance.thread_kwargs["base_instructions"])
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

    def test_openrouter_baseline_plus_uses_max_and_keeps_key_out_of_artifacts(self) -> None:
        import openai_codex
        from openai_codex.types import ReasoningEffort

        self.assertEqual(ReasoningEffort("max").value, "max")

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(openai_codex, "Codex", FakeCodex),
            patch("dotenv.dotenv_values", return_value={"OPENROUTER_API_KEY": "test-provider-secret"}),
            patch.dict("os.environ", {"AVO_OPENROUTER_KEY_FILE": ""}),
            patch("studies.codex_agent.session._find_codex_bin", return_value="codex"),
        ):
            with CodexGameSession(
                CodexSessionConfig(model="openrouter/qwen/qwen3.8-27b", effort="max", workspace_enabled=True),
                Path(tmpdir) / "workspace", artifact_directory=tmpdir,
            ) as session:
                response = session.next_action("frame")
                instance = FakeCodex.instances[-1]
                self.assertEqual(response["operation"], "ACT")
                self.assertEqual(instance.thread_kwargs["model"], "qwen/qwen3.8-27b")
                self.assertEqual(instance.thread.calls[0]["kwargs"]["effort"], "max")
                self.assertNotIn("output_schema", instance.thread.calls[0]["kwargs"])
                self.assertIn('After any tool calls finish', instance.thread_kwargs['base_instructions'])
                self.assertEqual(instance.config.env["OPENROUTER_API_KEY"], "test-provider-secret")
                self.assertIn('model_provider="openrouter"', instance.config.config_overrides)
                self.assertIn('model_providers.openrouter.requires_openai_auth=false', instance.config.config_overrides)
                self.assertIn("features.shell_tool=false", instance.config.config_overrides)
                self.assertIn("features.goals=false", instance.config.config_overrides)
                self.assertIn('mcp_servers.codex_notes.enabled_tools=["list_notes","read_note","write_note"]', instance.config.config_overrides)
                proxy_call = self.proxy_type.call_args.kwargs
                self.assertEqual(proxy_call["upstream_origin"], "https://openrouter.ai")
                self.assertEqual(proxy_call["base_path"], "/api/v1")
            for path in Path(tmpdir).rglob("*.json*"):
                self.assertNotIn("test-provider-secret", path.read_text(encoding="utf-8"))

    def test_openrouter_missing_key_fails_before_model_start(self) -> None:
        import openai_codex

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(openai_codex, "Codex") as codex,
            patch("dotenv.dotenv_values", return_value={}),
            patch.dict("os.environ", {"AVO_OPENROUTER_KEY_FILE": "", "OPENROUTER_API_KEY": ""}),
        ):
            with self.assertRaisesRegex(RuntimeError, "existing OPENROUTER_API_KEY"):
                with CodexGameSession(CodexSessionConfig(model="openrouter/qwen/qwen3.8-27b"), tmpdir):
                    pass
            codex.assert_not_called()

    def test_unconstrained_action_accepts_plain_or_fenced_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session = CodexGameSession(CodexSessionConfig(model="openrouter/qwen/qwen3.8-27b"), tmpdir)
            session._thread = object()
            for text in (
                '{"action":"ACTION1","note":"probe"}',
                'Notes saved.\n```json\n{"action":"ACTION1","note":"probe"}\n```',
                'I have my mapping recorded. Acting now.\n\n{"action":"ACTION1","note":"probe"}',
                '{"action":"ACTION1","note":"probe with {braces}"}\nAction selected.',
            ):
                with self.subTest(text=text), patch.object(session, "_run_with_retry", return_value=SimpleNamespace(final_response=text)):
                    response = session.next_action("frame")
                    self.assertEqual(response["action"], "ACTION1")
                    self.assertTrue(response["note"].startswith("probe"))

    def test_optional_note_and_extra_metadata_do_not_stop_actions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = CodexGameSession(CodexSessionConfig(), tmpdir)
            session._thread = object()
            for text in ('ACTION1', '{"action":"ACTION1"}', '{"action":"ACTION1","note":"probe","extra":true}'):
                with self.subTest(text=text), patch.object(session, "_run_with_retry", return_value=SimpleNamespace(final_response=text)):
                    self.assertEqual(session.next_action("frame")["action"], "ACTION1")

    def test_unconstrained_action_rejects_invalid_or_ambiguous_responses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session = CodexGameSession(CodexSessionConfig(model="openrouter/qwen/qwen3.8-27b"), tmpdir)
            session._thread = object()
            for text in (
                '{"action":"ACTION99","note":"probe"}',
                '{"action":"ACTION1","note":"a"}\n{"action":"ACTION2","note":"b"}',
                '```json\n{"action":"ACTION1","note":"a"}\n```\n```json\n{"action":"ACTION2","note":"b"}\n```',
            ):
                with self.subTest(text=text), patch.object(session, "_run_with_retry", return_value=SimpleNamespace(final_response=text)):
                    with self.assertRaises(ValueError):
                        session.next_action("frame")


if __name__ == "__main__":
    unittest.main()
