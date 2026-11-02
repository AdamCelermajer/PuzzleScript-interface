"""Command construction and event normalization for every harness (no model calls)."""
import json
import sys
from pathlib import Path

import pytest

from harnesses.antigravity import DENY_HOOK, AntigravitySession, install_web_deny_hook
from harnesses.base import EventLog, HarnessError, run_streaming
from harnesses.claude_code import ClaudeCodeSession
from harnesses.codex import CodexSession
from harnesses.opencode import OpenCodeSession
from harnesses.registry import create_session


@pytest.fixture(autouse=True)
def private_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_PRIVATE_ROOT", str(tmp_path / "private"))
    monkeypatch.setenv("HARNESS_ALLOW_HOST", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token")


def started(harness, tmp_path, model, effort="low", **kwargs):
    session = create_session(harness)
    return session.start(tmp_path / "ws", "SYSTEM PROMPT", model, effort, "player", tmp_path / "analysis", **kwargs)


def feed(session, lines):
    """Normalize raw CLI events the way CliSession.turn does."""
    session.turn_number += 1
    out = []
    for line in lines:
        for event in session.normalize(line):
            kind = event.pop("type")
            out.append(session.log.write(turn=session.turn_number, type=kind, session=session.session_id, **event))
    return out


# ---------------------------------------------------------------- codex
def test_codex_first_and_resumed_commands(tmp_path):
    session = started("codex", tmp_path, "gpt-5.6-sol")
    first = session.command("do it", [])
    assert first[1:6] == ["exec", "--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "-m"]
    assert "model_reasoning_effort=\"low\"" in first and 'web_search="disabled"' in first
    assert 'developer_instructions="SYSTEM PROMPT"' in first
    assert first[-2:] == ["--", "do it"] and "resume" not in first
    session.session_id = "thread-1"
    image = tmp_path / "frame.png"
    resumed = session.command("next", [image])
    assert resumed[resumed.index("resume"):] == ["resume", "-i", str(image), "--", "thread-1", "next"]


CODEX_EVENTS = [
    {"type": "thread.started", "thread_id": "019a-thread"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "i0", "type": "reasoning", "text": "**Thinking**"}},
    {"type": "item.completed", "item": {"id": "i1", "type": "command_execution", "command": "bash -lc ls",
                                        "aggregated_output": "frame.png\n", "exit_code": 0, "status": "completed"}},
    {"type": "item.completed", "item": {"id": "i2", "type": "file_change", "status": "completed",
                                        "changes": [{"path": "/w/notes/a.md", "kind": "add"}]}},
    {"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "{\"action\":\"ACTION1\"}"}},
    {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 7,
                                         "reasoning_output_tokens": 3}},
]


def test_codex_normalization(tmp_path):
    session = started("codex", tmp_path, "gpt-5.6-sol")
    events = feed(session, CODEX_EVENTS)
    assert [e["type"] for e in events] == ["reasoning", "command", "file_change", "message"]
    assert session.session_id == "019a-thread"
    assert events[1]["text"] == "bash -lc ls" and events[1]["exit_code"] == 0
    assert events[2]["text"] == "add /w/notes/a.md"
    assert session.final_text() == '{"action":"ACTION1"}'
    assert session._usage == {"input": 100, "output": 7, "reasoning": 3, "cached": 40}
    assert all(e["schema"] == "agent-event-v1" and e["harness"] == "codex" and e["role"] == "player" for e in events)


# ---------------------------------------------------------------- claude code
def test_claude_commands_session_id_resume_and_web_tools(tmp_path):
    session = started("claude-code", tmp_path, "claude-haiku-5-5", effort="max")
    first = session.command("hello", [])
    assert first[1:3] == ["-p", "hello"]
    assert first[first.index("--effort") + 1] == "max"
    assert first[first.index("--append-system-prompt") + 1] == "SYSTEM PROMPT"
    assert first[first.index("--session-id") + 1] == session.session_id
    assert first[-3:] == ["--disallowedTools", "WebSearch", "WebFetch"]
    assert "--dangerously-skip-permissions" in first
    assert session.env["CLAUDE_CONFIG_DIR"].startswith(str(tmp_path / "private"))
    resumed = session.command("again", [])
    assert resumed[resumed.index("--resume") + 1] == session.session_id and "--session-id" not in resumed


def test_claude_images_go_through_stream_json_stdin(tmp_path):
    session = started("claude-code", tmp_path, "claude-haiku-5-5")
    image = tmp_path / "frame.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nxx")
    command = session.command("look", [image])
    assert "look" not in command and command[command.index("--input-format") + 1] == "stream-json"
    payload = json.loads(session.stdin_payload("look", [image]))
    content = payload["message"]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["type"] == "image" and content[1]["source"]["media_type"] == "image/png"


CLAUDE_EVENTS = [
    {"type": "system", "subtype": "init", "session_id": "sess-1", "tools": ["Bash", "Read"]},
    {"type": "assistant", "session_id": "sess-1", "message": {"content": [
        {"type": "thinking", "thinking": "hmm"},
        {"type": "text", "text": "Let me look."},
        {"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "ls"}},
        {"type": "tool_use", "id": "tu2", "name": "Write", "input": {"file_path": "/w/notes/s.md", "content": "x"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu1", "content": "frame.png", "is_error": False},
        {"type": "tool_result", "tool_use_id": "tu2", "content": [{"type": "text", "text": "ok"}]}]}},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "ACTION4"}]}},
    {"type": "result", "subtype": "success", "is_error": False, "result": "ACTION4", "session_id": "sess-1",
     "total_cost_usd": 0.002, "usage": {"input_tokens": 10, "cache_read_input_tokens": 90,
                                        "cache_creation_input_tokens": 5, "output_tokens": 20}},
]


def test_claude_normalization(tmp_path):
    session = started("claude-code", tmp_path, "claude-haiku-5-5")
    events = feed(session, CLAUDE_EVENTS)
    assert [e["type"] for e in events] == ["reasoning", "message", "command", "file_change", "message"]
    assert events[2]["text"] == "ls" and events[2]["output"] == "frame.png" and events[2]["exit_code"] == 0
    assert events[3]["text"] == "/w/notes/s.md" and events[3]["output"] == "ok"
    assert session.session_id == "sess-1" and session.final_text() == "ACTION4"
    assert session._usage["input"] == 105 and session._usage["cached"] == 90 and session._usage["cost_usd"] == 0.002


# ---------------------------------------------------------------- opencode
def test_opencode_private_config_declares_model_and_denies_web(tmp_path):
    session = started("opencode", tmp_path, "openrouter/qwen/qwen3.8-27b", effort="max", provider="deepinfra")
    config = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())
    assert config["provider"]["openrouter"]["models"]["qwen/qwen3.8-27b"]["options"]["provider"] == {
        "order": ["deepinfra"], "allow_fallbacks": False}
    assert config["permission"]["*"] == "allow" and config["permission"]["webfetch"] == "deny"
    assert session.env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] == "64000"  # thinking models outlast the 32k default
    assert json.loads((session.analysis_dir / "session.json").read_text())["output_token_max"] == 64000
    assert Path(config["instructions"][0]).read_text() == "SYSTEM PROMPT"
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        assert session.env[name].startswith(str(tmp_path / "private"))
    command = session.command("play", [tmp_path / "f.png"])
    assert command[1:3] == ["run", "play"]
    assert command[command.index("-m") + 1] == "openrouter/qwen/qwen3.8-27b"
    assert command[command.index("--variant") + 1] == "xhigh" and command[-2:] == ["-f", str(tmp_path / "f.png")]
    session.session_id = "ses_1"
    assert session.command("again", [])[-2:] == ["--session", "ses_1"]


def test_opencode_qwen_gets_qwen_sampling_and_openrouter_gets_the_effort(tmp_path):
    # OpenCode alone would send temperature 0.55, top_p 1, no top_k and no effort for any "qwen" id.
    session = started("opencode", tmp_path, "openrouter/qwen/qwen3.8-27b", effort="high", provider="chutes")
    config = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())
    model = config["provider"]["openrouter"]["models"]["qwen/qwen3.8-27b"]
    assert model["temperature"] is True and model["options"]["top_k"] == 20
    assert model["options"]["reasoning"] == {"effort": "high"}
    assert config["agent"]["build"] == {"temperature": 1.0, "top_p": 0.95} and config["agent"]["title"] == {"disable": True}
    manifest = json.loads((session.analysis_dir / "session.json").read_text())
    assert manifest["effort_sent"] == "high" and manifest["sampling"].startswith("temperature 1.0")
    other = json.loads(Path(started("opencode", tmp_path / "o", "openrouter/google/gemini-3.5-flash").env["OPENCODE_CONFIG"]).read_text())
    assert other["agent"] == {"title": {"disable": True}}  # no title request to a second model
    assert "options" not in other["provider"]["openrouter"]["models"]["google/gemini-3.5-flash"]


def test_opencode_pins_a_nanogpt_host_strictly(tmp_path):
    session = started("opencode", tmp_path, "nanogpt/qwen/qwen3.8-27b:thinking", provider="deepinfra")
    config = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())
    assert config["provider"]["nanogpt"]["models"]["qwen/qwen3.8-27b:thinking"]["options"]["provider"] == {
        "only": ["deepinfra"], "allow_fallbacks": False}


def test_opencode_declares_the_real_context_of_openrouter_qwen_27b(tmp_path):
    # models.dev lists 1M tokens for this id; a pinned 262k host would reject the request before OpenCode compacts.
    session = started("opencode", tmp_path, "openrouter/qwen/qwen3.8-27b", provider="chutes")
    model = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())["provider"]["openrouter"]["models"]["qwen/qwen3.8-27b"]
    assert model["limit"] == {"context": 262144, "output": 64000}
    assert model["options"]["provider"] == {"order": ["chutes"], "allow_fallbacks": False}
    assert json.loads((session.analysis_dir / "session.json").read_text())["opencode_limit"]["context"] == 262144
    other = started("opencode", tmp_path / "other", "openrouter/qwen/qwen3.8-flash")
    assert "limit" not in json.loads(Path(other.env["OPENCODE_CONFIG"]).read_text())["provider"]["openrouter"]["models"]["qwen/qwen3.8-flash"]


def test_opencode_nanogpt_is_a_custom_openai_compatible_provider(tmp_path):
    session = started("opencode", tmp_path, "nanogpt/deepseek/deepseek-v4.1-flash")
    provider = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())["provider"]["nanogpt"]
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    # OpenCode calls the recorder, which forwards to NanoGPT.
    assert provider["options"]["apiKey"] == "{env:NANOGPT_API_KEY}"
    assert provider["options"]["baseURL"] == session.recorder_url + "/api/v1" and session.recorder.upstream == "https://nano-gpt.com"
    assert "deepseek/deepseek-v4.1-flash" in provider["models"]



def serve(monkeypatch, served=None, error=None):
    """Fake vLLM /v1/models for the vast provider."""
    import io
    import urllib.error
    calls = []

    def urlopen(url, timeout):
        calls.append(url)
        if error:
            raise urllib.error.URLError(error)
        return io.BytesIO(json.dumps({"data": served or []}).encode())
    monkeypatch.setattr("harnesses.opencode.urllib.request.urlopen", urlopen)
    return calls


def test_opencode_vast_declares_endpoint_limits_thinking_and_records_them(tmp_path, monkeypatch):
    monkeypatch.setenv("VAST_LLM_BASE_URL", "http://host.docker.internal:18100/v1/")
    calls = serve(monkeypatch, [{"id": "q3.8-27b-fp8", "root": "Qwen/Qwen3.8-27B-FP8", "max_model_len": 262144}])
    session = started("opencode", tmp_path, "vast/q3.8-27b-fp8")
    assert calls == ["http://host.docker.internal:18100/v1/models"]
    provider = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())["provider"]["vast"]
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert provider["options"]["apiKey"] == "unused" and provider["options"]["baseURL"] == session.recorder_url + "/v1"
    assert session.recorder.upstream == "http://host.docker.internal:18100"
    model = provider["models"]["q3.8-27b-fp8"]
    assert model["modalities"]["input"] == ["text", "image"] and model["attachment"] is True
    assert model["limit"] == {"context": 262144, "output": 64000}  # OpenCode compacts only with a declared limit
    assert model["options"] == {"chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "xhigh"}}
    manifest = json.loads((session.analysis_dir / "session.json").read_text())
    assert (manifest["endpoint"], manifest["served_model"], manifest["served_weights"]) == (
        "http://host.docker.internal:18100/v1", "q3.8-27b-fp8", "Qwen/Qwen3.8-27B-FP8")
    assert manifest["opencode_limit"] == {"context": 262144, "output": 64000} and manifest["image_input"] is True
    assert manifest["thinking"]["reasoning_effort"] == "xhigh" and manifest["sampling"].startswith("temperature 1.0")
    command = session.command("play", [])
    assert command[command.index("-m") + 1] == "vast/q3.8-27b-fp8"


def test_opencode_vast_fails_fast_when_the_endpoint_is_down_or_serves_another_model(tmp_path, monkeypatch):
    serve(monkeypatch, error="connection refused")
    with pytest.raises(HarnessError, match="SSH tunnel"):
        started("opencode", tmp_path / "a", "vast/q3.8-27b-fp8")
    serve(monkeypatch, [{"id": "other", "max_model_len": 1}])
    with pytest.raises(HarnessError, match="serves other, not q3.8-27b-fp8"):
        started("opencode", tmp_path / "b", "vast/q3.8-27b-fp8")


def test_opencode_declares_image_input_from_the_provider_model_list(tmp_path, monkeypatch):
    # Without a declared image modality OpenCode replaces -f frame.png with "does not support image input".
    lists = {"openrouter": {"qwen/qwen3.8-27b": {"architecture": {"input_modalities": ["text", "image"]}},
                            "text/only": {"architecture": {"input_modalities": ["text"]}}},
             "nanogpt": {"qwen/qwen3.8-flash": {"capabilities": {"vision": True}}}}
    monkeypatch.setattr("harnesses.opencode._model_list", lambda provider: lists[provider])

    def declared(model):
        session = started("opencode", tmp_path / model.replace("/", "_"), model)
        provider, native = model.split("/", 1)
        entry = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())["provider"][provider]["models"][native]
        manifest = json.loads((session.analysis_dir / "session.json").read_text())
        return entry.get("modalities", {}).get("input"), entry.get("attachment"), manifest["image_input"], manifest["image_input_source"]

    assert declared("openrouter/qwen/qwen3.8-27b") == (["text", "image"], True, True, "provider model list")
    assert declared("nanogpt/qwen/qwen3.8-flash") == (["text", "image"], True, True, "provider model list")
    assert declared("openrouter/text/only") == (None, None, False, "provider model list")
    assert declared("openrouter/unlisted/model") == (["text", "image"], True, True, "assumed (model not listed)")

OPENCODE_EVENTS = [
    {"type": "step_start", "sessionID": "ses_9", "part": {"type": "step-start"}},
    {"type": "text", "sessionID": "ses_9", "part": {"type": "text", "text": "Checking."}},
    {"type": "tool_use", "sessionID": "ses_9", "part": {"type": "tool", "tool": "bash", "state": {
        "status": "completed", "input": {"command": "ls"}, "output": "frame.png", "metadata": {"exit": 0}}}},
    {"type": "tool_use", "sessionID": "ses_9", "part": {"type": "tool", "tool": "write", "state": {
        "status": "completed", "input": {"filePath": "/w/notes/a.md"}, "output": ""}}},
    {"type": "step_finish", "sessionID": "ses_9", "part": {"tokens": {"input": 50, "output": 5, "reasoning": 2,
                                                                     "cache": {"read": 10, "write": 0}}, "cost": 0.001}},
    {"type": "text", "sessionID": "ses_9", "part": {"type": "text", "text": "ACTION2"}},
    {"type": "step_finish", "sessionID": "ses_9", "part": {"tokens": {"input": 60, "output": 1, "reasoning": 0,
                                                                     "cache": {"read": 50}}}},
]


def test_opencode_normalization(tmp_path):
    session = started("opencode", tmp_path, "openrouter/qwen/qwen3.8-27b")
    events = feed(session, OPENCODE_EVENTS)
    assert [e["type"] for e in events] == ["message", "command", "file_change", "message"]
    assert events[1]["exit_code"] == 0 and events[2]["text"] == "/w/notes/a.md"
    assert session.session_id == "ses_9" and session.final_text() == "ACTION2"
    assert session._usage["input"] == 110 and session._usage["cached"] == 60 and session._usage["output"] == 6


def test_opencode_compaction_summary_is_not_part_of_the_answer(tmp_path):
    # Seen on 21 Oct (vast.ai compaction test): summary text, synthetic "Continue ..." part, answer.
    session = started("opencode", tmp_path, "openrouter/qwen/qwen3.8-27b")
    feed(session, [
        {"type": "tool_use", "sessionID": "s", "part": {"type": "tool", "tool": "bash", "state": {"input": {"command": "cat f"}}}},
        {"type": "text", "sessionID": "s", "part": {"type": "text", "text": "## Goal\nsummary"}},
        {"type": "text", "sessionID": "s", "part": {"type": "text", "synthetic": True, "metadata": {"compaction_continue": True},
                                                    "text": "Continue if you have next steps"}},
        {"type": "text", "sessionID": "s", "part": {"type": "text", "text": "ACTION3"}},
    ])
    assert session.final_text() == "ACTION3"


# ---------------------------------------------------------------- antigravity
def test_antigravity_prefixes_system_prompt_once_and_installs_web_hook(tmp_path):
    session = started("antigravity", tmp_path, "gemini-3.8-flash-low")
    hooks = json.loads((tmp_path / "home/.gemini/config/hooks.json").read_text())
    assert hooks == DENY_HOOK and "search_web" in hooks["puzzlescript-no-web"]["PreToolUse"][0]["matcher"]
    assert (tmp_path / "home/.gemini/xdg-antigravity").is_dir()
    session.turn_number = 1
    first = session.command("go", [session.workspace / "frame.png"])
    assert first[first.index("-p") + 1].startswith("SYSTEM PROMPT\n\n---\n\ngo")
    assert "frame.png" in first[first.index("-p") + 1]
    assert "--dangerously-skip-permissions" in first and first[first.index("--effort") + 1] == "low"
    session.session_id, session.turn_number = "conv-1", 2
    resumed = session.command("next", [])
    assert resumed[resumed.index("-p") + 1] == "next" and resumed[-2:] == ["--conversation", "conv-1"]


def test_antigravity_hook_merges_with_existing_hooks(tmp_path):
    path = tmp_path / ".gemini/config/hooks.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mine": {"Stop": []}}))
    install_web_deny_hook(tmp_path / ".gemini")
    assert set(json.loads(path.read_text())) == {"mine", "puzzlescript-no-web"}


AGY_EVENTS = [
    {"event": "init", "init": {"conversation_id": "c-42", "tools": ["run_command", "view_file"]}},
    {"event": "step_update", "step_update": {"step_index": 1, "step_type": "agent_response", "text_delta": "Think"}},
    {"event": "step_update", "step_update": {"step_index": 2, "step_type": "tool", "tool_info": {
        "name": "run_command", "args": {"CommandLine": "ls"}, "output": "frame.png"}}},
    {"event": "step_update", "step_update": {"step_index": 2, "step_type": "tool", "tool_info": {
        "name": "run_command", "args": {"CommandLine": "ls"}, "output": "frame.png"}}},
    {"event": "step_update", "step_update": {"step_index": 3, "step_type": "agent_response", "text_delta": "ing"}},
    {"event": "result", "result": {"conversation_id": "c-42", "status": "SUCCESS", "response": "ACTION3",
                                   "usage": {"input_tokens": 9, "output_tokens": 4, "thinking_tokens": 2,
                                             "cache_read_tokens": 1, "total_tokens": 16}}},
]


def test_antigravity_normalization_and_observed_error_result(tmp_path):
    session = started("antigravity", tmp_path, "gemini-3.8-flash-low")
    events = feed(session, AGY_EVENTS)
    assert [e["type"] for e in events] == ["command", "message"]
    assert events[0]["text"] == "ls" and events[1]["text"] == "Thinking"
    assert session.session_id == "c-42" and session.final_text() == "ACTION3"
    assert session._usage == {"input": 9, "output": 4, "reasoning": 2, "cached": 1}
    # Captured 2026-10-15 from agy 1.3.5 in the image without a login.
    observed = {"event": "result", "result": {"conversation_id": "", "status": "ERROR", "response": "",
                                              "error": "authentication failed or timed out", "duration_seconds": 0,
                                              "num_turns": 0, "usage": {"input_tokens": 0}}}
    errors = feed(session, [observed])
    assert errors[-1]["type"] == "error" and "authentication" in errors[-1]["text"]


# ---------------------------------------------------------------- base turn plumbing
FAKE_CLI = r'''
import json, sys, time
print(json.dumps({"type": "thread.started", "thread_id": "t-1"}), flush=True)
print("not json", flush=True)
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": sys.argv[1]}}), flush=True)
if sys.argv[1] == "sleep":
    time.sleep(60)
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}}), flush=True)
'''


class FakeCodex(CodexSession):
    def command(self, instruction, images):
        return [sys.executable, str(self.script), instruction]


def test_turn_writes_raw_stdout_events_and_resumes(tmp_path):
    session = FakeCodex()
    session.start(tmp_path / "ws", "S", "gpt-5.6-sol", "low", "optimizer", tmp_path / "analysis")
    session.script = tmp_path / "fake.py"
    session.script.write_text(FAKE_CLI)
    result = session.turn("ACTION1")
    assert (result.text, result.session_id, result.exit_code, result.error) == ("ACTION1", "t-1", 0, "")
    raw = (tmp_path / "analysis/raw/turn-1.jsonl").read_text().splitlines()
    assert "not json" in raw and len(raw) == 4
    events = [json.loads(line) for line in (tmp_path / "analysis/agent_events.jsonl").read_text().splitlines()]
    assert [e["type"] for e in events] == ["message", "usage", "turn_end"]
    assert events[-1]["role"] == "optimizer" and events[-1]["usage"]["output"] == 2
    assert json.loads((tmp_path / "analysis/session.json").read_text())["harness"] == "codex"


def test_turn_timeout_kills_the_process(tmp_path):
    session = FakeCodex()
    session.start(tmp_path / "ws", "S", "gpt-5.6-sol", "low", "player", tmp_path / "analysis")
    session.script = tmp_path / "fake.py"
    session.script.write_text(FAKE_CLI)
    result = session.turn("sleep", timeout=3)
    assert result.timed_out and "timed out" in result.error and result.text == "sleep"


def test_run_streaming_closes_stdin(tmp_path):
    seen = []
    code, timed_out, _ = run_streaming([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
                                       cwd=tmp_path, env=dict(__import__("os").environ), timeout=30,
                                       raw_path=tmp_path / "raw.jsonl", on_line=seen.append)
    assert (code, timed_out, seen) == (0, False, ["''"])


def test_event_log_rejects_unknown_types_and_truncates(tmp_path):
    log = EventLog(tmp_path, harness="bare", model="m", role="player")
    record = log.write(turn=1, type="command", text="x" * 40_000)
    assert len(record["text"]) < 17_000
    with pytest.raises(ValueError):
        log.write(turn=1, type="bogus")


def test_start_validates_effort_and_model(tmp_path):
    with pytest.raises(HarnessError):
        started("codex", tmp_path, "gpt-5.6-sol", effort="minimal")
    with pytest.raises(HarnessError):
        started("claude-code", tmp_path, "gpt-5.6-sol")
    with pytest.raises(HarnessError):
        started("codex", tmp_path, "gpt-5.6-sol", provider="deepinfra")


def test_session_classes_are_registered():
    assert isinstance(create_session("codex"), CodexSession)
    assert isinstance(create_session("claude-code"), ClaudeCodeSession)
    assert isinstance(create_session("opencode"), OpenCodeSession)
    assert isinstance(create_session("antigravity"), AntigravitySession)
