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
            final_response=json.dumps(
                {"action": "ACTION4", "note": "move right"}
            )
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
    def test_uses_oauth_sdk_thread_with_sol_light_defaults(self) -> None:
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
                    CodexSessionConfig(),
                    Path(tmpdir),
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


if __name__ == "__main__":
    unittest.main()
