import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.core.framework import Action, AvoLaboratory, Comparison, Observation
from avo.core.profile import TaskEvaluation
from avo.core.tool_gateway import AvoToolGateway


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


class CodexOAuthAgentTests(unittest.TestCase):
    def test_uses_one_persistent_workspace_write_thread(self):
        with tempfile.TemporaryDirectory() as root:
            environment = IdleEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(lab, IdleProfile(environment), Path(root) / "trusted-candidates")
            with patch("openai_codex.Codex", FakeCodex), patch(
                "avo.client.codex_oauth_agent._find_codex_bin", return_value="codex"
            ):
                result = CodexOAuthAgent(CodexOAuthConfig(max_turns=1)).run(
                    gateway, Path(root) / "workspace"
                )

            self.assertEqual(result.turns, 1)
            self.assertIn("agent turn budget exhausted", result.finish_reason)
            self.assertEqual(len(FakeCodex.instance.thread.calls), 1)
            self.assertEqual(
                FakeCodex.instance.thread_settings["sandbox"].value,
                "workspace-write",
            )
            self.assertIn("unknown interactive environment", FakeCodex.instance.thread_settings["base_instructions"])

    def test_accepts_a_custom_tool_server_for_the_outer_loop(self):
        with tempfile.TemporaryDirectory() as root:
            environment = IdleEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(lab, IdleProfile(environment), Path(root) / "trusted-candidates")
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


if __name__ == "__main__":
    unittest.main()
