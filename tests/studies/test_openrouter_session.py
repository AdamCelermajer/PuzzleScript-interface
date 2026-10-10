import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from client.arc.types import GameAction, GameState
from studies.codex_agent.openrouter_session import OpenRouterGameSession, open_game_session
from studies.codex_agent.runner import CodexAgentRunner
from studies.codex_agent.session import CodexGameSession, CodexSessionConfig


class ScriptedChat:
    def __init__(self, model, effort, request_dir, **kwargs):
        self.effort, self.effort_sent, self.context_chars = effort, effort, 1
        self.calls = []
        self.replies = list(ScriptedChat.script)

    def complete(self, messages, tools=None, tool_choice=None):
        self.calls.append({"messages": json.loads(json.dumps(messages)), "tools": tools, "tool_choice": tool_choice})
        return self.replies.pop(0), {"reasoning": ""}


def session(tmp_path, harness, condition, script):
    ScriptedChat.script = script
    config = CodexSessionConfig(model="openrouter/vendor/model", effort="high", harness=harness,
                                workspace_enabled=condition == "baseline-plus")
    with patch("studies.codex_agent.openrouter_session.OpenRouterChat", ScriptedChat):
        game = open_game_session(config, tmp_path / "workspace", artifact_directory=tmp_path)
        game.__enter__()
    return game


def call(name, arguments, call_id):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def test_factory_keeps_codex_as_default_harness(tmp_path):
    config = CodexSessionConfig()
    assert isinstance(open_game_session(config, tmp_path / "w", tmp_path), CodexGameSession)


def test_tools_harness_executes_native_note_calls_then_returns_action(tmp_path):
    game = session(tmp_path, "tools", "baseline-plus", [
        {"role": "assistant", "content": "", "tool_calls": [call("write_note", {"path": "strategy.md", "content": "plan"}, "n1")]},
        {"role": "assistant", "content": 'Moving. {"action": "ACTION2", "note": "probe"}'},
    ])
    assert game.next_action("frame") == {"operation": "ACT", "action": "ACTION2", "note": "probe"}
    assert (tmp_path / "workspace" / "strategy.md").read_text(encoding="utf-8") == "plan"
    assert game.note_tool_count() == 1
    assert (tmp_path / "note_history" / "note_transitions.jsonl").exists()
    assert [tool["function"]["name"] for tool in game.chat.calls[0]["tools"]] == ["list_notes", "read_note", "write_note"]
    manifest = json.loads((tmp_path / "isolation_manifest.json").read_text(encoding="utf-8"))
    assert manifest["harness"] == "tools" and manifest["model_has_filesystem_or_shell"] is False


def test_raw_harness_runs_note_tags_and_accepts_action_in_same_reply(tmp_path):
    game = session(tmp_path, "raw", "baseline-plus", [
        {"role": "assistant", "content": '<write_note path="strategy.md">\nA1 is up {maybe}\n</write_note>\n{"action": "ACTION1"}'},
    ])
    assert game.next_action("frame")["action"] == "ACTION1"
    assert (tmp_path / "workspace" / "strategy.md").read_text(encoding="utf-8") == "A1 is up {maybe}\n"
    assert game.chat.calls[0]["tools"] is None
    assert "<write_note" in game.messages[0]["content"]


def test_raw_harness_returns_tag_results_when_no_action_was_given(tmp_path):
    game = session(tmp_path, "raw", "baseline-plus", [
        {"role": "assistant", "content": '<read_note path="missing.md"/>'},
        {"role": "assistant", "content": "ACTION3"},
    ])
    assert game.next_action("frame")["action"] == "ACTION3"
    assert "Tool results:" in game.chat.calls[1]["messages"][-1]["content"]


def test_tool_calls_at_round_limit_are_answered_before_correction(tmp_path, monkeypatch):
    monkeypatch.setattr("studies.codex_agent.openrouter_session.MAX_TOOL_ROUNDS", 1)
    looping = {"role": "assistant", "content": "", "tool_calls": [call("list_notes", {}, "x")]}
    game = session(tmp_path, "tools", "baseline-plus", [looping, looping])
    with pytest.raises(ValueError):
        game.next_action("frame")
    assert game.chat.calls[-1]["tool_choice"] == "none"
    assert game.messages[-1]["role"] == "tool"


def test_runner_turns_unavailable_action_into_a_correction(tmp_path):
    frame = SimpleNamespace(frame=[[[0]]], state=GameState.PLAYING, levels_completed=0, win_levels=1,
                            available_actions=[GameAction.ACTION1], rendered_frame=None)
    replies = iter([{"operation": "ACT", "action": "ACTION5", "note": ""},
                    {"operation": "ACT", "action": "ACTION1", "note": ""}])
    prompts = []

    class Session:
        def next_action(self, prompt, image_path=None):
            prompts.append(prompt)
            return next(replies)

    class Env:
        steps = []

        def reset(self):
            return frame

        def step(self, action):
            Env.steps.append(action)
            return frame

    runner = CodexAgentRunner(env=Env(), session=Session(), output_dir=tmp_path, max_steps=1)
    result = runner.run()
    assert Env.steps == [GameAction.ACTION1]
    assert result.decisions == 2
    assert "ACTION5 is not available" in prompts[1]
