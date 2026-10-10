import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from avo.client.codex_oauth_agent import (
    INNER_RUN_INSTRUCTION,
    CodexOAuthAgent,
    CodexOAuthConfig,
)
from avo.core.framework import Action, AvoLaboratory, Comparison, Observation
from avo.core.profile import TaskEvaluation
from avo.core.tool_gateway import AvoToolGateway
from avo.isolation import IsolatedRuntime, IsolationError


class IdleEnvironment:
    def reset(self):
        return Observation(payload={}, status="RUNNING", available_actions=("A1",))

    def step(self, action: Action):
        return self.reset()

    def compare(self, expected, actual):
        return Comparison(True, 1, 1, 1)


class IdleProfile:
    profile_id = "idle"
    objective = "Complete the idle task."

    def __init__(self, environment):
        self.environment = environment

    def evaluate(self, history, current):
        return TaskEvaluation(False, False, 0.0, {"success": 0})


class FakeTurn:
    id = "turn"

    def interrupt(self):
        return None

    def run(self):
        return type("Result", (), {"final_response": "done thinking"})()


class FakeThread:
    id = "thread"

    def __init__(self):
        self.calls = []

    def turn(self, inputs, **kwargs):
        self.calls.append((inputs, kwargs))
        return FakeTurn()


class FakeCodex:
    instance = None

    def __init__(self, config=None):
        self.config = config
        self.thread = FakeThread()
        self.thread_settings = None
        FakeCodex.instance = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def thread_start(self, **kwargs):
        self.thread_settings = kwargs
        return self.thread


class RecordingToolServer:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeProxy:
    model_base_url = "http://127.0.0.1:9/backend-api/codex"

    def __init__(self, *args, guard=None, **kwargs):
        self.guard = guard

    def start(self):
        pass

    def stop(self):
        pass


class CodexOAuthAgentTests(unittest.TestCase):
    def test_stale_tool_failure_flag_does_not_abort_the_model_turn(self):
        class FailedServer(RecordingToolServer):
            isolation_failure = "Old tool error"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            environment = IdleEnvironment()
            gateway = AvoToolGateway(AvoLaboratory(environment, [], root / "evidence"), IdleProfile(environment))
            server = FailedServer()
            with patch("openai_codex.Codex", FakeCodex), patch("avo.client.codex_oauth_agent._find_codex_bin", return_value="codex"):
                result = CodexOAuthAgent(CodexOAuthConfig(max_turns=1, analysis_dir=root / "analysis")).run(gateway, root / "workspace", tool_server=server)
            self.assertEqual(result.turns, 1)
            self.assertTrue(server.stopped)

    def test_openrouter_uses_same_codex_thread_and_permissions_with_qualified_provenance(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            environment = IdleEnvironment()
            gateway = AvoToolGateway(AvoLaboratory(environment, [], root/'evidence'), IdleProfile(environment))
            with patch('openai_codex.Codex', FakeCodex), patch(
                'avo.client.codex_oauth_agent._find_codex_bin', return_value='codex'
            ), patch.object(IsolatedRuntime, 'authenticate_openrouter') as router_auth, patch.object(
                IsolatedRuntime, 'authenticate'
            ) as oauth_auth:
                CodexOAuthAgent(CodexOAuthConfig(model='openrouter/vendor/model', max_turns=1,
                    analysis_dir=root/'analysis')).run(gateway, root/'workspace')
            router_auth.assert_called_once()
            oauth_auth.assert_not_called()
            self.assertEqual(FakeCodex.instance.thread_settings['model'], 'vendor/model')
            self.assertNotIn('sandbox', FakeCodex.instance.thread_settings)
            overrides = FakeCodex.instance.config.config_overrides
            self.assertIn('model_provider="openrouter"', overrides)
            self.assertIn('model_providers.openrouter.env_key="OPENROUTER_API_KEY"', overrides)
            self.assertFalse(any(value.startswith('openai_base_url=') for value in overrides))
            manifest = json.loads((root/'analysis/session.json').read_text())
            self.assertEqual(manifest['model'], 'openrouter/vendor/model')
            self.assertEqual(manifest['metadata']['model_provider'], 'openrouter')

    def test_outer_final_report_is_one_extra_turn_in_same_thread_after_search_closes(self):
        from avo.evolution.gateway import EvolutionGateway
        from avo.evolution.store import EvolutionStore
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = EvolutionStore.create(root / "campaign", root / "workspace")
            gateway = EvolutionGateway(store, None, mission="test", world_model_mode="final-only")
            with patch("openai_codex.Codex", FakeCodex), patch(
                "avo.client.codex_oauth_agent._find_codex_bin", return_value="codex"
            ):
                result = CodexOAuthAgent(CodexOAuthConfig(max_turns=1)).run(
                    gateway, root / "workspace", tool_server=RecordingToolServer()
                )
            self.assertEqual(result.turns, 4)
            self.assertEqual(len(FakeCodex.instance.thread.calls), 4)
            self.assertIn("Write world_model.md", str(FakeCodex.instance.thread.calls[1]))
            self.assertIn("was not saved", str(FakeCodex.instance.thread.calls[2]))
            self.assertIn("was not saved", str(FakeCodex.instance.thread.calls[3]))
            self.assertIn("research-note style", str(FakeCodex.instance.thread.calls[2]))
            self.assertIn("research-note style", str(FakeCodex.instance.thread.calls[3]))
            self.assertNotIn("world_model.md", str(FakeCodex.instance.thread.calls[0]))
            self.assertIsNone(gateway.finalization_instruction())
            with self.assertRaises(RuntimeError):
                gateway.handle("evaluate", {"candidate_id": "x_0001"})

    def setUp(self):
        for target, kwargs in (
            ("avo.client.codex_oauth_agent.IsolatedRuntime.preflight", {"return_value": {"passed": True}}),
            ("avo.client.codex_oauth_agent.IsolatedRuntime.authenticate", {"return_value": None}),
            ("avo.client.codex_oauth_agent.CodexRequestProxy", {"new": FakeProxy}),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_inner_uses_bounded_discovery_run_instruction(self):
        agent = CodexOAuthAgent(CodexOAuthConfig(session_role="inner_player"))

        self.assertEqual(agent._initial_instruction(), INNER_RUN_INSTRUCTION)
        self.assertIn("bounded discovery phase", INNER_RUN_INSTRUCTION)
        self.assertIn("encode untried outcomes as unknown", INNER_RUN_INSTRUCTION)
        self.assertIn("do not repeat it unless the model or context changed", INNER_RUN_INSTRUCTION)
        self.assertIn("graph-changing model update", INNER_RUN_INSTRUCTION)

    def test_uses_one_persistent_workspace_write_thread_without_memories(self):
        with tempfile.TemporaryDirectory() as root:
            environment = IdleEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(lab, IdleProfile(environment))
            with patch("openai_codex.Codex", FakeCodex), patch(
                "avo.client.codex_oauth_agent._find_codex_bin", return_value="codex"
            ):
                result = CodexOAuthAgent(CodexOAuthConfig(max_turns=1)).run(
                    gateway, Path(root) / "workspace"
                )

            self.assertEqual(result.turns, 1)
            self.assertIn("agent turn budget exhausted", result.finish_reason)
            self.assertEqual(len(FakeCodex.instance.thread.calls), 1)
            self.assertNotIn("sandbox", FakeCodex.instance.thread_settings)
            self.assertEqual(FakeCodex.instance.config.cwd, str(Path(root) / "workspace"))
            self.assertIn("CODEX_HOME", FakeCodex.instance.config.env)
            self.assertIsNone(FakeCodex.instance.thread_settings["service_tier"])
            self.assertEqual(
                FakeCodex.instance.config.config_overrides[:3],
                (
                    "features.memories=false",
                    "memories.use_memories=false",
                    "memories.generate_memories=false",
                ),
            )
            self.assertIn("unknown interactive environment", FakeCodex.instance.thread_settings["base_instructions"])
            self.assertIn("Never inspect parent directories", FakeCodex.instance.thread_settings["base_instructions"])

    def test_accepts_a_custom_tool_server_for_the_outer_loop(self):
        with tempfile.TemporaryDirectory() as root:
            environment = IdleEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(lab, IdleProfile(environment))
            server = RecordingToolServer()
            with patch("openai_codex.Codex", FakeCodex), patch(
                "avo.client.codex_oauth_agent._find_codex_bin", return_value="codex"
            ):
                CodexOAuthAgent(CodexOAuthConfig(max_turns=1)).run(
                    gateway,
                    Path(root) / "workspace",
                    tool_server=server,
                )

            self.assertTrue(server.started)
            self.assertTrue(server.stopped)

    def test_passes_fast_service_tier_to_codex_thread(self):
        with tempfile.TemporaryDirectory() as root:
            environment = IdleEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(lab, IdleProfile(environment))
            with patch("openai_codex.Codex", FakeCodex), patch(
                "avo.client.codex_oauth_agent._find_codex_bin", return_value="codex"
            ):
                CodexOAuthAgent(
                    CodexOAuthConfig(max_turns=1, service_tier="priority")
                ).run(gateway, Path(root) / "workspace")

            self.assertEqual(
                FakeCodex.instance.thread_settings["service_tier"], "priority"
            )

    def test_writes_session_artifacts_and_requests_transport_capture(self):
        with tempfile.TemporaryDirectory() as root:
            environment = IdleEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(lab, IdleProfile(environment))
            analysis = Path(root) / "analysis"
            with patch("openai_codex.Codex", FakeCodex), patch(
                "avo.client.codex_oauth_agent._find_codex_bin",
                return_value="patched-codex",
            ):
                CodexOAuthAgent(
                    CodexOAuthConfig(
                        max_turns=1,
                        analysis_dir=analysis,
                        session_role="outer_optimizer",
                    )
                ).run(gateway, Path(root) / "workspace")

            session = json.loads((analysis / "session.json").read_text())
            prompt = json.loads((analysis / "prompt.json").read_text())
            turn = json.loads((analysis / "turn_inputs.jsonl").read_text().strip())
            self.assertEqual(session["role"], "outer_optimizer")
            self.assertEqual(session["thread_id"], "thread")
            self.assertEqual(session["status"], "completed")
            self.assertIn("unknown interactive environment", prompt["base_instructions"])
            self.assertEqual(turn["turn_id"], "turn")
            self.assertTrue(
                any(
                    value.startswith('openai_base_url="http://127.0.0.1:')
                    for value in FakeCodex.instance.config.config_overrides
                )
            )


if __name__ == "__main__":
    unittest.main()
