"""Registry, launcher, in-container entry, bare loop, baseline wipe and the AVO CliAgent."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harnesses import entry, launch
from harnesses.base import HarnessError, TurnResult
from harnesses.registry import HARNESS_IDS, HARNESSES, credentials_for, list_harnesses, resolve_model_for


@pytest.fixture(autouse=True)
def private_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_PRIVATE_ROOT", str(tmp_path / "private"))
    monkeypatch.setenv("HARNESS_ALLOW_HOST", "1")


# ---------------------------------------------------------------- registry
@pytest.mark.parametrize("harness,model,expected", [
    ("codex", "gpt-5.6-sol", ("openai", "gpt-5.6-sol")),
    ("claude-code", "claude-haiku-5-5", ("anthropic", "claude-haiku-5-5")),
    ("opencode", "openrouter/qwen/qwen3.8-27b", ("openrouter", "qwen/qwen3.8-27b")),
    ("bare", "nanogpt/deepseek/deepseek-v4.1-flash", ("nanogpt", "deepseek/deepseek-v4.1-flash")),
    ("antigravity", "gemini-3.8-flash-high", ("google", "gemini-3.8-flash-high")),
])
def test_models_resolve_per_harness(harness, model, expected):
    assert resolve_model_for(harness, model) == expected


@pytest.mark.parametrize("harness,model", [
    ("codex", "openrouter/qwen/qwen3.8-27b"), ("codex", "claude-haiku-5-5"), ("claude-code", "gpt-5.6-sol"),
    ("opencode", "gpt-5.6-sol"), ("bare", "openrouter/qwen"), ("antigravity", "openrouter/a/b"), ("nope", "x"),
])
def test_wrong_model_for_harness_is_rejected(harness, model):
    with pytest.raises(HarnessError):
        resolve_model_for(harness, model)


def test_listing_shape_readiness_and_models_hook():
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "x", "OPENROUTER_API_KEY": "y"}
    listing = {entry["id"]: entry for entry in list_harnesses(env=env, models_hook=lambda p: [{"id": f"{p}/a/b"}])}
    assert tuple(listing) == HARNESS_IDS
    for entry in listing.values():
        assert {"id", "label", "providers", "models", "efforts", "ready", "missing"} <= set(entry)
        assert entry["efforts"] == ["low", "medium", "high", "xhigh", "max"]
    assert listing["claude-code"]["ready"] and listing["opencode"]["ready"]
    assert listing["opencode"]["models"] == [{"id": "openrouter/a/b", "label": "openrouter/a/b"},
                                             {"id": "nanogpt/a/b", "label": "nanogpt/a/b"}]
    assert not list_harnesses(env={})[1]["ready"]
    assert HARNESSES["claude-code"]["models"][0]["id"].startswith("claude-")


def test_credentials_are_per_harness_and_provider():
    assert credentials_for("codex", ["gpt-5.6-sol"]) == ["codex-auth"]
    assert credentials_for("claude-code", ["claude-haiku-5-5"]) == ["CLAUDE_CODE_OAUTH_TOKEN"]
    assert credentials_for("antigravity", ["gemini-3.8-flash-low"]) == ["agy-volume"]
    assert credentials_for("bare", ["openrouter/a/b", "nanogpt/c"]) == ["NANOGPT_API_KEY", "OPENROUTER_API_KEY"]


# ---------------------------------------------------------------- launch
def test_sessions_refuse_to_run_on_the_host(tmp_path, monkeypatch):
    from harnesses import base
    monkeypatch.delenv("HARNESS_ALLOW_HOST")
    monkeypatch.delenv("HARNESS_CONTAINER", raising=False)
    monkeypatch.setattr(base, "in_container", lambda: False)
    from harnesses.registry import create_session
    with pytest.raises(HarnessError, match="container"):
        create_session("bare").start(tmp_path, "S", "openrouter/a/b", "low", "player", tmp_path / "a")


def options(**overrides):
    values = dict(mode="baseline-plus", harness="claude-code", model="claude-haiku-5-5", optimizer_model="",
                  optimizer_effort="", effort="low", game_id="ps_modality-v1",
                  backend_url="http://host.docker.internal:8000", output_dir="", max_wall_seconds=0, max_steps=3,
                  max_evaluations=None, research_moves=None, solver_moves=None, world_model_mode="final-only",
                  provider="", resume=False, continue_from="")
    values.update(overrides)
    return argparse.Namespace(**values)


def test_backend_url_rewrites_host_loopback():
    assert launch.container_backend_url("http://localhost:8000") == "http://host.docker.internal:8000"
    assert launch.container_backend_url("http://127.0.0.1:8001/x") == "http://host.docker.internal:8001/x"
    assert launch.container_backend_url("http://host.docker.internal:8000") == "http://host.docker.internal:8000"


def test_run_spec_matches_contract_fields():
    spec = launch.run_spec(options())
    assert spec["schema"] == "run-spec-v1" and spec["budget"] == {"max_wall_seconds": 0, "max_steps": 3}
    assert "optimizer_model" not in spec and spec["continued_from"] is None
    campaign = launch.run_spec(options(mode="campaign", harness="opencode", model="openrouter/qwen/qwen3.8-27b",
                                       max_evaluations=2, research_moves=30, solver_moves=40, max_steps=None))
    assert campaign["optimizer_model"] == "openrouter/qwen/qwen3.8-27b"
    assert campaign["budget"] == {"max_wall_seconds": 0, "max_evaluations": 2, "research_moves": 30, "solver_moves": 40}
    assert campaign["world_model_mode"] == "final-only"


@pytest.mark.parametrize("overrides", [
    {"mode": "campaign"}, {"max_steps": None}, {"provider": "deepinfra"}, {"resume": True},
    {"harness": "codex"}, {"max_wall_seconds": -1},
    {"mode": "campaign", "max_evaluations": 1, "research_moves": 1, "solver_moves": 1, "continue_from": "x"},
])
def test_invalid_launch_options(overrides):
    with pytest.raises(HarnessError):
        launch.validate(options(**overrides))


def test_docker_command_is_plain_non_root_container(tmp_path):
    command = launch.docker_command("ps-agent-x", tmp_path / "c", tmp_path / "o", ["--env", "K"], ["-m", "harnesses.entry"])
    assert command[:5] == ["docker", "run", "--name", "ps-agent-x", "--rm"]
    joined = " ".join(command)
    assert "--cap-drop ALL" in joined and "no-new-privileges" in joined and "--cap-add" not in joined
    assert "--privileged" not in joined and "seccomp" not in joined
    assert f"src={tmp_path / 'c'},dst=/controller,readonly" in joined and f"src={tmp_path / 'o'},dst=/results" in joined
    assert command[-3:] == [launch.IMAGE, "-m", "harnesses.entry"] and "--env" in command


def test_stage_controller_excludes_games_env_outputs_and_tests(tmp_path):
    root = tmp_path / "repo"
    for name in ("avo/evolve.py", "avo/output/run/x.py", "avo/tests/test_x.py", "client/arc/types.py",
                 "client/rules/g/rules.json", "harnesses/base.py", "harnesses/docker/Dockerfile",
                 "studies/__init__.py", "studies/codex_agent/run.py", "studies/codex_agent/output/r/a.md",
                 "studies/other/secret.py", "puzzlescript_interface/games/g/script.txt", ".env", "avo/.env"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x")
    target = tmp_path / "staged"
    launch.stage_controller(target, root)
    staged = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
    assert staged == ["avo/evolve.py", "client/arc/types.py", "harnesses/base.py", "studies/__init__.py",
                      "studies/codex_agent/run.py"]


def test_credentials_stage_only_the_chosen_harness(tmp_path, monkeypatch):
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "auth.json").write_text(json.dumps({"tokens": {"a": 1}}))
    monkeypatch.setenv("CODEX_HOME", str(home))
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "secret-claude", "OPENROUTER_API_KEY": "secret-or"}
    (tmp_path / "creds-codex").mkdir()
    opts, child = launch.stage_credentials("codex", ["gpt-5.6-sol"], tmp_path / "creds-codex", env)
    assert (tmp_path / "creds-codex/auth.json").is_file() and child == {}
    assert any("dst=/credentials,readonly" in item for item in opts)
    opts, child = launch.stage_credentials("claude-code", ["claude-haiku-5-5"], tmp_path, env)
    assert opts == ["--env", "CLAUDE_CODE_OAUTH_TOKEN"] and child == {"CLAUDE_CODE_OAUTH_TOKEN": "secret-claude"}
    assert "secret" not in " ".join(opts)
    monkeypatch.setattr(launch, "docker_object_exists", lambda kind, name: True)
    opts, _ = launch.stage_credentials("antigravity", ["gemini-3.8-flash-low"], tmp_path, env)
    assert opts == ["--mount", f"type=volume,src={launch.AGY_VOLUME},dst=/home/agent/.gemini"]
    with pytest.raises(HarnessError):
        launch.stage_credentials("opencode", ["nanogpt/x"], tmp_path, env)
    monkeypatch.setattr(launch, "docker_object_exists", lambda kind, name: False)
    with pytest.raises(HarnessError, match="login antigravity"):
        launch.stage_credentials("antigravity", ["gemini-3.8-flash-low"], tmp_path, env)


def test_resume_requires_same_harness_and_maps_legacy_names(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "lineage.json").write_text("{}")
    (campaign / "evolution_config.json").write_text(json.dumps(
        {"harness": "tools", "provider": "", "profile_settings": {"game_id": "ps_modality-v1"},
         "world_model_mode": "final-only"}))
    launch.check_resume(options(mode="campaign", harness="bare", resume=True), tmp_path)
    with pytest.raises(HarnessError, match="harness"):
        launch.check_resume(options(mode="campaign", harness="opencode", resume=True), tmp_path)
    with pytest.raises(HarnessError, match="game"):
        launch.check_resume(options(mode="campaign", harness="bare", game_id="other"), tmp_path)


def test_dry_run_prints_command_without_writing(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test")
    output = tmp_path / "run"
    code = launch.launch(["--mode", "baseline", "--harness", "bare", "--model", "openrouter/qwen/qwen3.8-27b",
                          "--effort", "low", "--game-id", "g", "--backend-url", "http://localhost:8000",
                          "--max-steps", "2", "--output-dir", str(output), "--dry-run"])
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and not output.exists()
    assert printed["run_spec"]["backend_url"] == "http://host.docker.internal:8000"
    assert printed["command"][-3:] == ["harnesses.entry", "--spec", "/results/run_spec.json"]
    assert "--env" in printed["command"] and "OPENROUTER_API_KEY" in printed["command"]


# ---------------------------------------------------------------- entry
SPEC = {"schema": "run-spec-v1", "mode": "campaign", "harness": "opencode", "model": "openrouter/qwen/qwen3.8-27b",
        "optimizer_model": "openrouter/qwen/qwen3.8-27b", "effort": "high", "optimizer_effort": "low",
        "game_id": "ps_modality-v1", "backend_url": "http://host.docker.internal:8000",
        "budget": {"max_wall_seconds": 0, "max_evaluations": 8, "research_moves": 400, "solver_moves": 300},
        "world_model_mode": "between-hypotheses", "provider": "deepinfra", "continued_from": None}


def test_entry_campaign_argv():
    argv = entry.campaign_argv(SPEC, resume=True, results=Path("/results"))

    def value(flag):
        return argv[argv.index(flag) + 1]
    assert argv[0] == "avo.evolve" and argv[-1] == "--resume-saved-campaign"
    assert value("--harness") == "opencode" and value("--optimizer-effort") == "low" and value("--player-effort") == "high"
    assert value("--player-max-environment-steps") == "400" and value("--fresh-solver-max-environment-steps") == "300"
    assert value("--max-wall-seconds") == "0" and value("--world-model-mode") == "between-hypotheses"
    assert value("--provider") == "deepinfra" and "game_id=ps_modality-v1" in argv
    assert Path(value("--output-dir")).as_posix() == "/results/campaign"


def test_entry_baseline_argv_and_continuation():
    spec = {**SPEC, "mode": "baseline-plus", "harness": "claude-code", "model": "claude-haiku-5-5", "provider": "",
            "budget": {"max_wall_seconds": 60, "max_steps": 3}, "continued_from": "C:/runs/parent"}
    argv = entry.baseline_argv(spec, results=Path("/results"), parent=Path("/parent"))
    assert argv[:2] == ["studies.codex_agent.run", "--no-window"]
    assert argv[argv.index("--condition") + 1] == "baseline-plus" and argv[argv.index("--max-steps") + 1] == "3"
    assert argv[argv.index("--max-wall-seconds") + 1] == "60"
    assert Path(argv[argv.index("--continue-from") + 1]).as_posix() == "/parent"


def test_entry_copies_codex_auth_into_a_writable_home(tmp_path, monkeypatch):
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "auth.json").write_text('{"tokens": {}}')
    monkeypatch.delenv("CODEX_HOME", raising=False)
    entry.prepare_credentials("codex", credentials, tmp_path / "home")
    assert (tmp_path / "home/.codex/auth.json").read_text() == '{"tokens": {}}'
    import os
    assert os.environ["CODEX_HOME"] == str(tmp_path / "home/.codex")
    monkeypatch.delenv("CODEX_HOME")


# ---------------------------------------------------------------- bare loop
class ScriptedChat:
    replies = []

    def __init__(self, *args, **kwargs):
        self.calls = []

    def complete(self, messages, tools=None, tool_choice=None):
        self.calls.append([dict(m) for m in messages])
        return ScriptedChat.replies.pop(0), {"usage": {"prompt_tokens": 5, "completion_tokens": 1}}


def test_bare_loop_runs_tools_without_credentials(tmp_path, monkeypatch):
    from harnesses.bare import BareSession
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak")
    command = "echo ${OPENROUTER_API_KEY:-none}" if __import__("os").name != "nt" else "echo $env:OPENROUTER_API_KEY; echo none"
    ScriptedChat.replies = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "1", "function": {"name": "shell", "arguments": json.dumps({"command": command})}},
            {"id": "2", "function": {"name": "write_file", "arguments": json.dumps({"path": "notes/a.md", "content": "hi"})}},
            {"id": "3", "function": {"name": "read_file", "arguments": json.dumps({"path": "../escape.txt"})}}]},
        {"role": "assistant", "content": "ACTION1"},
    ]
    monkeypatch.setattr(BareSession, "chat_factory", ScriptedChat)
    session = BareSession().start(tmp_path / "ws", "S", "openrouter/a/b", "low", "player", tmp_path / "analysis")
    result = session.turn("go")
    assert result.text == "ACTION1" and (tmp_path / "ws/notes/a.md").read_text() == "hi"
    kinds = [event["type"] for event in result.events]
    assert kinds == ["command", "file_change", "tool", "message", "usage", "turn_end"]
    assert "must-not-leak" not in result.events[0]["output"]
    assert result.events[2]["exit_code"] == 1 and result.usage["input"] == 10
    assert session.messages[0]["content"].startswith("S") and (tmp_path / "analysis/raw/turn-1.jsonl").is_file()


# ---------------------------------------------------------------- direct player session
class FakeHarness:
    def __init__(self):
        self.turn_number = 0
        self.provider = "anthropic"
        self.workspace = None

    def start(self, workspace, prompt, model, effort, role, analysis, provider=""):
        self.workspace, self.prompt = Path(workspace), prompt
        return self

    def turn(self, instruction, images=(), timeout=None):
        self.turn_number += 1
        (self.workspace / "scratch.py").write_text("x")
        (self.workspace / "tmpdir").mkdir(exist_ok=True)
        notes = self.workspace / "notes"
        if notes.is_dir():
            (notes / "strategy.md").write_text(f"turn {self.turn_number}")
        assert all(Path(image).name == "frame.png" for image in images)
        return TurnResult(text='{"action": "ACTION2"}', session_id="s", usage={},
                          events=[{"type": "file_change"}, {"type": "message"}])

    def close(self):
        pass


@pytest.mark.parametrize("enabled,kept", [(False, ["frame.png"]), (True, ["frame.png", "notes"])])
def test_baseline_wipe_keeps_only_frames_and_notes(tmp_path, monkeypatch, enabled, kept):
    from studies.codex_agent import session as module
    monkeypatch.setattr("harnesses.registry.create_session", lambda harness: FakeHarness())
    frame = tmp_path / "f.png"
    frame.write_bytes(b"png")
    config = module.GameSessionConfig(model="claude-haiku-5-5", harness="claude-code", workspace_enabled=enabled)
    workspace, output = tmp_path / "ws", tmp_path / "out"
    with module.CliGameSession(config, workspace, output, mirror_directory=output / "workspace") as game:
        assert game.next_action("p", frame) == {"operation": "ACT", "action": "ACTION2", "note": ""}
        assert sorted(path.name for path in workspace.iterdir()) == kept
        game.next_action("p", frame)
        assert game.note_tool_count() == 2
    assert ("notes" in module.game_instructions(enabled)) is enabled
    if enabled:
        assert (output / "workspace/notes/strategy.md").read_text() == "turn 2"
    manifest = json.loads((output / "isolation_manifest.json").read_text())
    assert manifest["harness"] == "claude-code" and "delete everything else" in manifest["workspace_policy"]


# ---------------------------------------------------------------- AVO CliAgent
class Gateway:
    def __init__(self, finish_after=1, finalizer=None):
        self.finish_reason, self.terminal, self.turns, self.finished = "", False, 0, False
        self.finish_after = finish_after
        if finalizer:
            self.finalization_instruction = finalizer

    def handle(self, method, params=None):
        if method == "finish":
            self.finished, self.finish_reason = True, params["reason"]
        return {"budgets": {"wall_seconds_remaining": None}, "task": {"terminal": False}, "finished": self.finished}


class AgentHarness(FakeHarness):
    instructions = []

    def turn(self, instruction, images=(), timeout=None):
        AgentHarness.instructions.append((instruction, timeout))
        if "world_model.md" in instruction and len(AgentHarness.instructions) >= 3:
            (self.workspace / "world_model.md").write_text("model")
        return TurnResult(text="done", session_id="s", usage={}, events=[{"type": "message"}])


def test_cli_agent_drives_turns_and_report_retries(tmp_path, monkeypatch):
    from avo.client.turns import INNER_RUN_INSTRUCTION, AgentConfig, CliAgent
    monkeypatch.setattr("harnesses.registry.create_session", lambda harness: AgentHarness())
    AgentHarness.instructions = []
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("base")
    agent = CliAgent(AgentConfig(model="claude-haiku-5-5", harness="claude-code", prompt_path=prompt, max_turns=1,
                                 analysis_dir=tmp_path / "analysis", session_role="inner_player"))
    server = SimpleNamespace(start=lambda: None, stop=lambda: None)
    result = agent.run(Gateway(finalizer=lambda: "Write world_model.md now."), tmp_path / "ws", tool_server=server)
    sent = [item[0] for item in AgentHarness.instructions]
    assert sent[0] == INNER_RUN_INSTRUCTION and sent[1] == "Write world_model.md now."
    assert sent[2].startswith("The required world_model.md was not saved") and len(sent) == 3
    assert result.finish_reason == "agent turn budget exhausted (1)" and result.turns == 3
    assert AgentHarness.instructions[1][1] == 300.0  # fixed report grace


def test_cli_agent_raises_when_the_cli_fails_without_working(tmp_path, monkeypatch):
    from avo.client.turns import AgentConfig, CliAgent

    class Broken(FakeHarness):
        def turn(self, instruction, images=(), timeout=None):
            return TurnResult(text="", session_id="", usage={}, events=[{"type": "error"}], exit_code=1,
                              error="not logged in")
    monkeypatch.setattr("harnesses.registry.create_session", lambda harness: Broken())
    prompt = tmp_path / "p.txt"
    prompt.write_text("x")
    agent = CliAgent(AgentConfig(model="gpt-5.6-sol", harness="codex", prompt_path=prompt, analysis_dir=tmp_path / "a"))
    with pytest.raises(HarnessError, match="not logged in"):
        agent.run(Gateway(), tmp_path / "ws", tool_server=SimpleNamespace(start=lambda: None, stop=lambda: None))
