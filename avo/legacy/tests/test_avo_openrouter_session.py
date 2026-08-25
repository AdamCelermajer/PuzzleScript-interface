import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from avo.legacy.openrouter_session import OpenRouterAvoConfig, OpenRouterAvoSession


def _response(*, content="", tool_calls=None, prompt_tokens=10, completion_tokens=5):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls or [],
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class OpenRouterAvoSessionTests(unittest.TestCase):
    def test_tool_loop_reads_workspace_then_returns_plan(self) -> None:
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="read_file",
                arguments=json.dumps({"path": "current_state.json"}),
            ),
        )
        client = FakeClient(
            [
                _response(tool_calls=[tool_call]),
                _response(
                    content=json.dumps(
                        {
                            "actions": ["ACTION4"],
                            "prediction": "move",
                            "note": "probe",
                            "confidence": "low",
                        }
                    )
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "current_state.json").write_text(
                '{"game":"unknown-game"}', encoding="utf-8"
            )
            session = OpenRouterAvoSession(
                OpenRouterAvoConfig(), workspace, client=client
            )
            plan = session.next_plan("play")

            self.assertEqual(plan["actions"], ["ACTION4"])
            second_messages = client.chat.completions.calls[1]["messages"]
            tool_results = [item for item in second_messages if item["role"] == "tool"]
            self.assertEqual(len(tool_results), 1)
            self.assertIn("unknown-game", tool_results[0]["content"])
            self.assertEqual(
                client.chat.completions.calls[0]["tool_choice"], "auto"
            )
            self.assertIn(
                "Current workspace snapshot",
                client.chat.completions.calls[0]["messages"][1]["content"],
            )
            self.assertTrue(client.chat.completions.calls[0]["parallel_tool_calls"])
            self.assertEqual(session.usage_summary()["requests"], 2)

    def test_bounded_helper_can_be_written_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "helpers").mkdir()
            session = OpenRouterAvoSession(
                OpenRouterAvoConfig(), workspace, client=FakeClient([])
            )
            written = json.loads(
                session._execute_tool(
                    "write_file",
                    {
                        "path": "helpers/solver.py",
                        "content": "print('solution=RRDD')\n",
                    },
                )
            )
            executed = json.loads(
                session._execute_tool(
                    "run_python", {"path": "helpers/solver.py", "args": []}
                )
            )

            self.assertTrue(written["ok"])
            self.assertTrue(executed["ok"])
            self.assertIn("solution=RRDD", executed["stdout"])

    def test_tool_paths_cannot_escape_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session = OpenRouterAvoSession(
                OpenRouterAvoConfig(), tmpdir, client=FakeClient([])
            )
            with self.assertRaisesRegex(ValueError, "not allowed"):
                session._execute_tool("read_file", {"path": "../secret.txt"})


if __name__ == "__main__":
    unittest.main()
