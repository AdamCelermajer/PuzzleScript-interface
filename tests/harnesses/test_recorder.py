import base64
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from harnesses.opencode import opencode_config
from harnesses.recorder import CallRecorder

PNG = base64.b64encode(b"\x89PNG fake").decode()


def fake_model():
    """An upstream that streams one reply: reasoning, text and a tool call, then usage."""
    seen = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            seen.append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            chunks = [{"provider": "Host", "choices": [{"delta": {"reasoning": "I think "}}]},
                      {"choices": [{"delta": {"reasoning": "so.", "content": "Go"}}]},
                      {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "bash", "arguments": '{"command":'}}]}}]},
                      {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"ls"}'}}]}, "finish_reason": "tool_calls"}],
                       "usage": {"prompt_tokens": 7}}]
            body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def test_recorder_forwards_each_call_unchanged_and_saves_it_with_its_images(tmp_path):
    server, seen = fake_model()
    recorder = CallRecorder(tmp_path / "calls", turn=lambda: 3, session=lambda: "s1",
                            upstream=f"http://127.0.0.1:{server.server_address[1]}")
    base = recorder.start() + "/api/v1"
    body = {"model": "m", "messages": [{"role": "user", "content": [
        {"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}]}]}
    request = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer secret", "Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        streamed = response.read().decode()
    recorder.stop()
    server.shutdown()
    assert seen[0][0] == "/api/v1/chat/completions" and seen[0][1] == "Bearer secret" and seen[0][2] == body
    saved = json.loads((tmp_path / "calls/0001.json").read_text(encoding="utf-8"))
    assert saved["turn"] == 3 and saved["session"] == "s1" and saved["status"] == 200 and saved["images"] == ["0001-image-1.png"]
    assert saved["request"]["messages"][0]["content"][1]["image_url"]["url"] == "[image saved as 0001-image-1.png]"
    assert (tmp_path / "calls/0001-image-1.png").read_bytes() == b"\x89PNG fake"
    assert (tmp_path / "calls/0001.response.txt").read_text(encoding="utf-8") == streamed
    assert saved["response"] == {"reasoning": "I think so.", "content": "Go", "finish_reason": "tool_calls",
                                 "tool_calls": [{"id": "c1", "name": "bash", "arguments": '{"command":"ls"}'}],
                                 "provider": "Host", "usage": {"prompt_tokens": 7}}
    assert "secret" not in (tmp_path / "calls/0001.json").read_text(encoding="utf-8")
    assert saved["headers"]["Content-Type"] == "application/json" and "Authorization" not in saved["headers"]


def test_recorder_numbers_after_calls_already_saved(tmp_path):
    (tmp_path / "calls").mkdir()
    (tmp_path / "calls/0004.json").write_text("{}", encoding="utf-8")
    recorder = CallRecorder(tmp_path / "calls", turn=lambda: 1)
    recorder.start()
    recorder.stop()
    assert recorder.count == 4


def test_opencode_sends_every_provider_through_the_recorder(tmp_path):
    for provider in ("openrouter", "nanogpt"):
        config = opencode_config(provider, "vendor/model", tmp_path / "s.md", base_url="http://127.0.0.1:5")
        assert config["provider"][provider]["options"]["baseURL"] == "http://127.0.0.1:5"


def test_one_view_of_chat_anthropic_and_responses_requests():
    from harnesses.recorder import view
    chat = view({"model": "m", "messages": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": "[image saved as 0001-image-1.png]"}}]},
        {"role": "assistant", "content": "", "reasoning_content": "hmm", "tool_calls": [{"id": "c", "function": {"name": "bash", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c", "content": "out"}], "tools": [{"type": "function", "function": {"name": "bash"}}]})
    assert chat["dialect"] == "chat-completions" and chat["system"] == ["S"] and chat["settings"] == {"model": "m"}
    assert [p["kind"] for m in chat["messages"] for p in m["parts"]] == ["text", "image", "reasoning", "tool_call", "tool_result"]
    assert chat["messages"][1]["parts"][0]["field"] == "reasoning_content" and chat["tools"][0]["name"] == "bash"
    anthropic = view({"model": "c", "system": [{"type": "text", "text": "S1"}], "messages": [
        {"role": "user", "content": [{"type": "image", "source": {"type": "base64", "data": "[image saved as 0002-image-1.png]"}}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "t"}, {"type": "tool_use", "id": "u", "name": "Bash", "input": {"command": "ls"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "u", "content": "files"}]}], "tools": [{"name": "Bash"}]})
    assert anthropic["dialect"] == "anthropic-messages" and anthropic["system"] == ["S1"]
    assert [p["kind"] for m in anthropic["messages"] for p in m["parts"]] == ["image", "reasoning", "tool_call", "tool_result"]
    responses = view({"model": "g", "instructions": "I", "input": [
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "dev"}]},
        {"type": "reasoning", "summary": [], "encrypted_content": "x"},
        {"type": "function_call", "name": "exec_command", "arguments": "{}", "call_id": "f"},
        {"type": "function_call_output", "call_id": "f", "output": "done"}]})
    assert responses["dialect"] == "openai-responses" and responses["system"] == ["I", "dev"]  # developer = system
    assert [p["kind"] for m in responses["messages"] for p in m["parts"]] == ["reasoning", "tool_call", "tool_result"]
    assert responses["messages"][0]["parts"][0]["text"] == "[encrypted reasoning]"


def test_assemble_reads_anthropic_and_responses_streams():
    from harnesses.recorder import assemble
    anthropic = "".join(f"event: x\ndata: {json.dumps(e)}\n\n" for e in [
        {"type": "message_start", "message": {"model": "c", "usage": {"input_tokens": 5}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hm"}},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "u", "name": "Bash"}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"a":1}'}},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 3}}])
    reply = assemble(anthropic.encode())
    assert reply["reasoning"] == "hm" and reply["tool_calls"] == [{"id": "u", "name": "Bash", "arguments": '{"a":1}'}]
    assert reply["finish_reason"] == "tool_use" and reply["usage"] == {"input_tokens": 5, "output_tokens": 3}
    responses = "".join(f"data: {json.dumps(e)}\n\n" for e in [
        {"type": "response.output_text.delta", "delta": "Hi"},
        {"type": "response.output_item.added", "item": {"type": "function_call", "id": "i", "call_id": "f", "name": "exec_command"}},
        {"type": "response.function_call_arguments.delta", "item_id": "i", "delta": "{}"},
        {"type": "response.completed", "response": {"model": "g", "status": "completed", "usage": {"input_tokens": 2}}}])
    reply = assemble(responses.encode())
    assert reply["content"] == "Hi" and reply["tool_calls"] == [{"id": "f", "name": "exec_command", "arguments": "{}"}]
    assert reply["finish_reason"] == "completed" and reply["model"] == "g"


def test_opencode_adds_the_callers_tools_in_its_private_config(tmp_path, monkeypatch):
    from harnesses.opencode import OpenCodeSession
    from frameworks.baseline.prompt import TOOLS
    monkeypatch.setattr("harnesses.opencode.image_input", lambda provider, model: True)
    monkeypatch.setenv("HARNESS_PRIVATE_ROOT", str(tmp_path / "private"))
    monkeypatch.setenv("HARNESS_ALLOW_HOST", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    session = OpenCodeSession()
    session.game_tools = [{**tool, "command": ["python", "/opt/game/game.py", "do"]} for tool in TOOLS["agent"]]
    session.start(tmp_path / "ws", "S", "openrouter/qwen/qwen3.8-27b", "low", "player", tmp_path / "analysis")
    try:
        tools = session.private / "xdg_config_home" / "opencode" / "tools"
        assert sorted(p.name for p in tools.iterdir()) == ["do.ts"]
        source = (tools / "do.ts").read_text()
        assert "Bun.$`python /opt/game/game.py do ${args.action}`" in source and json.dumps(str(session.workspace)) in source
        assert not (session.workspace / ".opencode").exists()  # nothing in the agent's own folder
        assert json.loads((tmp_path / "analysis" / "session.json").read_text())["game_tools"] == ["do"]
    finally:
        session.close()


def test_codex_input_with_developer_prompts_and_additional_tools():
    from harnesses.recorder import view
    shown = view({"model": "gpt", "input": [
        {"type": "additional_tools", "role": "developer", "tools": [{"type": "namespace", "name": "functions", "tools": [
            {"type": "custom", "name": "exec"}, {"type": "function", "name": "wait"}]}]},
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "You are Codex."}]},
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "Ours."},
                                                             {"type": "input_text", "text": "Skills."}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Play."}]}]})
    assert shown["system"] == ["You are Codex.", "Ours.\nSkills."]
    assert [t["name"] for t in shown["tools"]] == ["exec", "wait"]
    assert [m["role"] for m in shown["messages"]] == ["user"]


def test_opencode_lean_puts_our_prompt_in_place_of_opencodes_and_drops_coding_tools(tmp_path):
    config = opencode_config("openrouter", "qwen/qwen3.8-27b", tmp_path / "SYSTEM_PROMPT.md", lean=True)
    assert "instructions" not in config
    assert config["agent"]["build"]["prompt"] == "{file:" + str(tmp_path / "SYSTEM_PROMPT.md") + "}"
    assert config["agent"]["build"]["temperature"] == 1.0  # the Qwen sampling stays
    assert {tool: config["permission"][tool] for tool in ("skill", "todowrite", "task", "webfetch")} == {
        "skill": "deny", "todowrite": "deny", "task": "deny", "webfetch": "deny"}
    plain = opencode_config("openrouter", "qwen/qwen3.8-27b", tmp_path / "SYSTEM_PROMPT.md")
    assert plain["instructions"] and "prompt" not in plain["agent"].get("build", {}) and "skill" not in plain["permission"]
