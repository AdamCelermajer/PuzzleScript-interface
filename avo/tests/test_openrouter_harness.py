import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avo.client.codex_oauth_agent import CodexOAuthConfig
from avo.client.openrouter_agent import OpenRouterShellAgent, make_agent
from avo.client.openrouter_chat import OpenRouterChat, image_part
from avo.core.framework import AvoLaboratory
from avo.core.tool_gateway import AvoToolGateway
from avo.tests.test_avo_codex_oauth_agent import IdleEnvironment, IdleProfile

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


class ScriptedChat:
    """Stands in for OpenRouterChat; replays assistant messages in order."""

    instances = []

    def __init__(self, model, effort, request_dir, **kwargs):
        self.model, self.effort, self.effort_sent, self.context_chars = model, effort, effort, 1
        self.calls = []
        self.replies = list(ScriptedChat.script)
        ScriptedChat.instances.append(self)

    def complete(self, messages, tools=None, tool_choice=None):
        self.calls.append({"messages": json.loads(json.dumps(messages)), "tools": tools, "tool_choice": tool_choice})
        reply = self.replies.pop(0) if self.replies else {"role": "assistant", "content": "done"}
        return reply, {"reasoning": ""}


class EchoRuntime:
    """No-sandbox runtime: the command prints itself so outputs are checkable."""

    def __init__(self, workspace, artifacts, codex_bin):
        self.workspace, self.artifacts, self.codex_bin = Path(workspace), Path(artifacts), codex_bin
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.env = None
        self.commands = []

    def command(self, *args):
        self.commands.append(args[-1])
        return [sys.executable, "-c", f"print({args[-1]!r})"]

    def close(self):
        pass


def tool_call(name, arguments, call_id="c1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


class OpenRouterChatViewTests(unittest.TestCase):
    def test_only_newest_image_is_sent_and_old_groups_are_dropped_whole(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "a.png").write_bytes(PNG)
            (root / "b.png").write_bytes(PNG)
            with patch("avo.client.openrouter_chat.openrouter_key", return_value="k"):
                chat = OpenRouterChat("vendor/model", "max", root / "requests", context_chars=1_000_000)
            self.assertEqual(chat.effort_sent, "xhigh")
            with patch("avo.client.openrouter_chat.openrouter_key", return_value="k"):
                pinned = OpenRouterChat("vendor/model", "low", root / "requests", provider="alibaba")
            with patch.object(pinned, "_post", return_value={"choices": [{"message": {"content": "ok"}}]}) as post:
                pinned.complete([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
            self.assertEqual(json.loads(post.call_args.args[0])["provider"],
                             {"order": ["alibaba"], "allow_fallbacks": False})
            messages = [
                {"role": "system", "content": "s"},
                {"role": "user", "content": [{"type": "text", "text": "first"}, image_part(root / "a.png")]},
                {"role": "assistant", "content": "", "tool_calls": [tool_call("write_note", {"path": "x.md", "content": "y"})]},
                {"role": "tool", "tool_call_id": "c1", "content": "ok"},
                {"role": "user", "content": [{"type": "text", "text": "second"}, image_part(root / "b.png")]},
            ]
            view = chat._view(messages)
            self.assertEqual(view[1]["content"][1], {"type": "text", "text": "[earlier frame image omitted]"})
            self.assertTrue(view[4]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

            chat.context_chars = 1_200
            messages.insert(2, {"role": "user", "content": "x" * 5_000})
            trimmed = chat._view(messages)
            roles = [message["role"] for message in trimmed]
            # The tool result is never kept without the assistant call it answers.
            self.assertNotIn("x" * 5_000, json.dumps(trimmed))
            for index, role in enumerate(roles):
                if role == "tool":
                    self.assertEqual(roles[index - 1], "assistant")
            self.assertIn("removed to fit the context budget", json.dumps(trimmed))


class OpenRouterShellAgentTests(unittest.TestCase):
    def run_agent(self, harness, script):
        ScriptedChat.script = script
        ScriptedChat.instances = []
        root = Path(tempfile.mkdtemp())
        environment = IdleEnvironment()
        gateway = AvoToolGateway(AvoLaboratory(environment, [], root / "evidence"), IdleProfile(environment))
        with patch("avo.client.openrouter_agent.OpenRouterChat", ScriptedChat), patch(
                "avo.client.openrouter_agent.IsolatedRuntime", EchoRuntime), patch(
                "avo.client.openrouter_agent._find_codex_bin", return_value="codex"):
            agent = make_agent(CodexOAuthConfig(model="openrouter/vendor/model", max_turns=1, harness=harness,
                                                analysis_dir=root / "analysis"))
            self.assertIsInstance(agent, OpenRouterShellAgent)
            result = agent.run(gateway, root / "workspace")
        return root, result, ScriptedChat.instances[0]

    def test_raw_harness_runs_bash_blocks_without_tool_schema(self):
        root, result, chat = self.run_agent("raw", [
            {"role": "assistant", "content": "Check.\n```bash\npython avo_tool.py status\n```"},
            {"role": "assistant", "content": "All done."},
        ])
        self.assertEqual(result.turns, 1)
        self.assertIsNone(chat.calls[0]["tools"])
        self.assertIn("no function-calling interface", chat.calls[0]["messages"][0]["content"])
        output = chat.calls[1]["messages"][-1]["content"]
        self.assertIn("[exit code 0]", output)
        self.assertIn("python avo_tool.py status", output)
        conversation = (root / "analysis" / "conversation.jsonl").read_text(encoding="utf-8")
        self.assertIn('"commandExecution"', conversation)

    def test_tools_harness_answers_every_call_and_keeps_writes_in_workspace(self):
        root, _, chat = self.run_agent("tools", [
            {"role": "assistant", "content": "", "tool_calls": [
                tool_call("write_file", {"path": "notes/plan.md", "content": "plan"}, "a"),
                tool_call("write_file", {"path": "../escape.md", "content": "x"}, "b"),
                tool_call("shell", {"command": "echo hi"}, "c")]},
            {"role": "assistant", "content": "finished"},
        ])
        self.assertEqual([tool["function"]["name"] for tool in chat.calls[0]["tools"]],
                         ["shell", "read_file", "write_file", "view_image"])
        answers = {m["tool_call_id"]: m["content"] for m in chat.calls[1]["messages"] if m["role"] == "tool"}
        self.assertEqual(set(answers), {"a", "b", "c"})
        self.assertIn("inside the workspace", answers["b"])
        self.assertEqual((root / "workspace" / "notes" / "plan.md").read_text(encoding="utf-8"), "plan")
        self.assertFalse((root / "escape.md").exists())

    def test_raw_harness_longer_fence_keeps_inner_backticks(self):
        from avo.client.openrouter_agent import _BASH_BLOCK
        text = "````bash\ncat > a.md <<'EOF'\n```python\nx = 1\n```\nEOF\n````\nthen\n```bash\nls\n```"
        self.assertEqual([match.group(2) for match in _BASH_BLOCK.finditer(text)],
                         ["cat > a.md <<'EOF'\n```python\nx = 1\n```\nEOF\n", "ls\n"])


if __name__ == "__main__":
    unittest.main()


class WallClockGateway:
    """Search budget already exhausted; the report must still be requested with grace."""

    def __init__(self):
        self.finished, self.finish_reason, self.terminal = False, "", False
        self.reported = False

    def finalization_instruction(self):
        if self.reported:
            return None
        self.reported = True
        return "Write world_model.md now."

    def handle(self, method, params=None):
        if method == "finish":
            self.finished, self.finish_reason = True, params["reason"]
        return {"finished": self.finished, "budgets": {"wall_seconds_remaining": 0.0}, "task": {"terminal": False}}


def test_wall_exhaustion_still_requests_final_report_with_grace(tmp_path):
    from avo.client.codex_oauth_agent import REPORT_GRACE_SECONDS, drive_turns
    gateway, calls = WallClockGateway(), []

    def run_turn(number, instruction, timeout):
        calls.append((instruction, timeout))
        if instruction.startswith("Write world_model"):
            (tmp_path / "world_model.md").write_text("report", encoding="utf-8")
        return "ok"

    turns, _ = drive_turns(gateway, CodexOAuthConfig(max_turns=4), tmp_path, tmp_path / "t.jsonl", None, run_turn)
    assert turns == 2
    assert calls[1] == ("Write world_model.md now.", REPORT_GRACE_SECONDS)
    assert gateway.finish_reason == "wall-time budget exhausted"
