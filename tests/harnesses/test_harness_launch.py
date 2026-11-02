"""Registry, launcher, in-container entry, bare loop, baseline workspace and the AVO CliAgent."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harnesses import entry, launch
from harnesses.base import HarnessError, TurnResult
from frameworks.avo.framework import AVO
from frameworks.baseline.framework import BASELINE
from frameworks.harness2.framework import HARNESS2
from frameworks.registry import FRAMEWORKS, list_frameworks
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
    ("opencode", "vast/q3.8-27b-fp8", ("vast", "q3.8-27b-fp8")),
    ("antigravity", "gemini-3.8-flash-high", ("google", "gemini-3.8-flash-high")),
])
def test_models_resolve_per_harness(harness, model, expected):
    assert resolve_model_for(harness, model) == expected


@pytest.mark.parametrize("harness,model", [
    ("codex", "openrouter/qwen/qwen3.8-27b"), ("codex", "claude-haiku-5-5"), ("claude-code", "gpt-5.6-sol"),
    ("opencode", "gpt-5.6-sol"), ("bare", "openrouter/qwen"), ("antigravity", "openrouter/a/b"), ("nope", "x"),
    ("bare", "vast/q3.8-27b-fp8"), ("opencode", "vast/"),
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
                                             {"id": "nanogpt/a/b", "label": "nanogpt/a/b"},
                                             {"id": "vast/a/b", "label": "vast/a/b"}]
    assert not list_harnesses(env={})[1]["ready"]
    assert HARNESSES["claude-code"]["models"][0]["id"].startswith("claude-")


def test_credentials_are_per_harness_and_provider():
    assert credentials_for("codex", ["gpt-5.6-sol"]) == ["codex-auth"]
    assert credentials_for("claude-code", ["claude-haiku-5-5"]) == ["CLAUDE_CODE_OAUTH_TOKEN"]
    assert credentials_for("antigravity", ["gemini-3.8-flash-low"]) == ["agy-volume"]
    assert credentials_for("bare", ["openrouter/a/b", "nanogpt/c"]) == ["NANOGPT_API_KEY", "OPENROUTER_API_KEY"]
    assert credentials_for("opencode", ["vast/q3.8-27b-fp8"]) == ["VAST_LLM_BASE_URL"]


def test_vast_endpoint_is_staged_with_its_default_and_never_the_account_key(tmp_path):
    docker, child = launch.stage_credentials("opencode", ["vast/q3.8-27b-fp8"], tmp_path, env={})
    assert docker == ["--env", "VAST_LLM_BASE_URL"] and child == {"VAST_LLM_BASE_URL": "http://host.docker.internal:18100/v1"}
    _, child = launch.stage_credentials("opencode", ["vast/q3.8-27b-fp8"], tmp_path,
                                        env={"VAST_LLM_BASE_URL": "http://other:1/v1", "VAST_API_KEY": "account-secret"})
    assert child == {"VAST_LLM_BASE_URL": "http://other:1/v1"}
    assert list_harnesses(env={})[HARNESS_IDS.index("opencode")]["ready"]  # no key needed
    with pytest.raises(HarnessError):
        launch.validate(options(harness="opencode", model="vast/q3.8-27b-fp8", provider="deepinfra"), BASELINE)


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
    values = dict(framework="baseline", harness="claude-code", model="claude-haiku-5-5", optimizer_model="",
                  optimizer_effort="", effort="low", game_id="ps_modality-v1",
                  backend_url="http://host.docker.internal:8000", output_dir="", max_wall_seconds=0, max_steps=3,
                  notes=True, max_evaluations=None, research_moves=None, solver_moves=None, world_model_mode=None,
                  provider="", resume=False, continue_from="")
    values.update(overrides)
    return argparse.Namespace(**values)


def test_backend_url_rewrites_host_loopback():
    assert launch.container_backend_url("http://localhost:8000") == "http://host.docker.internal:8000"
    assert launch.container_backend_url("http://127.0.0.1:8001/x") == "http://host.docker.internal:8001/x"
    assert launch.container_backend_url("http://host.docker.internal:8000") == "http://host.docker.internal:8000"


def test_run_spec_records_framework_and_options():
    spec = launch.run_spec(options(), BASELINE)
    assert spec["schema"] == "run-spec-v2" and spec["framework"] == "baseline"
    assert spec["options"] == {"max_steps": 3, "driver": "controller", "memento": False, "start": "",
                               "stop_after_levels": 0, "start_level": 1, "one_level": False} and spec["max_wall_seconds"] == 0
    assert spec["optimizer_model"] is None and spec["continued_from"] is None
    campaign = launch.run_spec(options(framework="avo", harness="opencode", model="openrouter/qwen/qwen3.8-27b",
                                       max_evaluations=2, research_moves=30, max_steps=None, notes=None), AVO)
    assert campaign["optimizer_model"] == "openrouter/qwen/qwen3.8-27b" and campaign["optimizer_effort"] == "low"
    assert campaign["options"] == {"max_evaluations": 2, "research_moves": 30, "solver_moves": 400,
                                   "world_model_mode": "final-only", "fitness": "solver",
                                   "research_moves_schedule": "", "attempt_world_model": False, "final_solver": False,
                                   "continue_levels": False}


@pytest.mark.parametrize("overrides", [
    {"provider": "deepinfra"}, {"harness": "codex"}, {"max_wall_seconds": -1},
])
def test_invalid_launch_options(overrides):
    with pytest.raises(HarnessError):
        launch.validate(options(**overrides), BASELINE)


def test_nanogpt_host_pin_needs_opencode():
    launch.validate(options(harness="opencode", model="nanogpt/qwen/qwen3.8-27b:thinking", provider="deepinfra"), BASELINE)
    with pytest.raises(HarnessError, match="NanoGPT"):
        launch.validate(options(harness="bare", model="nanogpt/qwen/qwen3.8-27b:thinking", provider="deepinfra"), BASELINE)


@pytest.mark.parametrize("given", [{"max_steps": 0}, {"notes": True}, {"research_moves": 5}])
def test_framework_options_are_checked(given):
    with pytest.raises(ValueError):
        BASELINE.check_options(given)


def test_registry_describes_every_framework():
    listing = {entry["id"]: entry for entry in list_frameworks()}
    assert set(listing) == set(FRAMEWORKS) and json.dumps(listing)
    assert listing["avo"]["optimizer"] and listing["avo"]["restart"] == "resume"
    assert BASELINE.variant_label({}) == "Baseline" and AVO.variant_label({}) == "AVO · solver score"  # older AVO runs
    assert AVO.variant_label({"fitness": "research"}) == "AVO · research score"
    assert BASELINE.variant_label({"notes": False}) == "Baseline · no notes (old)"  # recorded before 21 Oct
    for framework in FRAMEWORKS.values():
        framework.check_options({})  # every default is valid


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
    for name in ("frameworks/avo/evolve.py", "frameworks/avo/output/run/x.py", "frameworks/avo/tests/test_x.py",
                 "game/types.py",
                 "harnesses/base.py", "harnesses/docker/Dockerfile", "frameworks/registry.py",
                 "frameworks/baseline/run.py", "frameworks/harness2/run.py", "avo/output/r/a.md", "studies/other/secret.py",
                 "puzzlescript_interface/games/g/script.txt", ".env", "frameworks/avo/.env"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x")
    target = tmp_path / "staged"
    launch.stage_controller(target, root)
    staged = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
    assert staged == ["frameworks/avo/evolve.py", "frameworks/baseline/run.py",
                      "frameworks/harness2/run.py", "frameworks/registry.py", "game/types.py", "harnesses/base.py"]


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


def test_avo_resume_requires_same_harness_and_maps_legacy_names(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "lineage.json").write_text("{}")
    (campaign / "evolution_config.json").write_text(json.dumps(
        {"harness": "tools", "provider": "", "profile_settings": {"game_id": "ps_modality-v1"},
         "world_model_mode": "final-only"}))
    spec = {"harness": "bare", "provider": "", "game_id": "ps_modality-v1",
            "options": {"world_model_mode": "final-only"}}
    AVO.check_restart(spec, tmp_path)
    with pytest.raises(ValueError, match="harness"):
        AVO.check_restart({**spec, "harness": "opencode"}, tmp_path)
    with pytest.raises(ValueError, match="game"):
        AVO.check_restart({**spec, "game_id": "other"}, tmp_path)


def launch_args(tmp_path, *extra):
    return ["--harness", "bare", "--model", "openrouter/qwen/qwen3.8-27b", "--effort", "low", "--game-id", "g",
            "--backend-url", "http://localhost:8000", "--output-dir", str(tmp_path / "run"), "--dry-run", *extra]


def test_dry_run_prints_command_without_writing(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test")
    code = launch.launch(["--framework", "baseline", "--max-steps", "2", *launch_args(tmp_path)])
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and not (tmp_path / "run").exists()
    assert printed["run_spec"]["backend_url"] == "http://host.docker.internal:8000"
    assert printed["run_spec"]["options"] == {"max_steps": 2, "driver": "controller", "memento": False, "start": "",
                                              "stop_after_levels": 0, "start_level": 1, "one_level": False}
    assert printed["command"][-3:] == ["harnesses.entry", "--spec", "/results/run_spec.json"]
    assert "--env" in printed["command"] and "OPENROUTER_API_KEY" in printed["command"]


@pytest.mark.parametrize("extra", [
    ["--framework", "baseline", "--max-evaluations", "2"],   # another framework's option
    ["--framework", "baseline", "--resume"],                 # baseline continues; only avo resumes
    ["--framework", "avo", "--continue-from", "x"],          # avo resumes; only baseline continues
    ["--framework", "avo", "--world-model-mode", "never"],
    ["--framework", "other"],
])
def test_launch_rejects_flags_of_other_frameworks(tmp_path, monkeypatch, extra):
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test")
    with pytest.raises(SystemExit):
        launch.launch([*extra, *launch_args(tmp_path)])


def test_launch_refuses_a_used_output_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test")
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "run_spec.json").write_text("{}")
    with pytest.raises(SystemExit):
        launch.launch(["--framework", "baseline", *launch_args(tmp_path)])


# ---------------------------------------------------------------- entry
SPEC = {"schema": "run-spec-v2", "framework": "avo", "harness": "opencode", "model": "openrouter/qwen/qwen3.8-27b",
        "optimizer_model": "openrouter/qwen/qwen3.8-27b", "effort": "high", "optimizer_effort": "low",
        "game_id": "ps_modality-v1", "backend_url": "http://host.docker.internal:8000", "max_wall_seconds": 0,
        "options": {"max_evaluations": 8, "research_moves": 400, "solver_moves": 300,
                    "world_model_mode": "between-hypotheses"},
        "provider": "deepinfra", "continued_from": None}


def test_avo_entry_argv():
    argv = AVO.entry(SPEC, True, Path("/results"), Path("/parent"))

    def value(flag):
        return argv[argv.index(flag) + 1]
    assert argv[0] == "frameworks.avo.evolve" and argv[-1] == "--resume-saved-campaign"
    assert value("--harness") == "opencode" and value("--optimizer-effort") == "low" and value("--player-effort") == "high"
    assert value("--player-max-environment-steps") == "400" and value("--fresh-solver-max-environment-steps") == "300"
    assert value("--max-wall-seconds") == "0" and value("--world-model-mode") == "between-hypotheses"
    assert value("--provider") == "deepinfra" and "game_id=ps_modality-v1" in argv
    assert Path(value("--output-dir")).as_posix() == "/results/campaign"
    assert value("--fitness") == "solver"  # a spec from before the fitness option
    research = AVO.entry({**SPEC, "options": {**SPEC["options"], "fitness": "research"}}, False, Path("/r"), Path("/p"))
    assert research[research.index("--fitness") + 1] == "research"


def test_avo_resume_keeps_the_fitness(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "lineage.json").write_text("{}")
    (campaign / "evolution_config.json").write_text(json.dumps(
        {"harness": "opencode", "provider": "deepinfra", "profile_settings": {"game_id": "ps_modality-v1"},
         "world_model_mode": "between-hypotheses"}))  # recorded before the fitness option: solver
    AVO.check_restart(SPEC, tmp_path)
    with pytest.raises(ValueError, match="fitness"):
        AVO.check_restart({**SPEC, "options": {**SPEC["options"], "fitness": "research"}}, tmp_path)


def test_baseline_entry_argv_and_continuation():
    spec = {**SPEC, "framework": "baseline", "harness": "claude-code", "model": "claude-haiku-5-5", "provider": "",
            "max_wall_seconds": 60, "options": {"max_steps": 3}, "continued_from": "C:/runs/parent"}
    argv = BASELINE.entry(spec, False, Path("/results"), Path("/parent"))
    assert argv[:2] == ["frameworks.baseline.run", "--notes"]
    assert "--notes" in argv and argv[argv.index("--max-steps") + 1] == "3"
    assert argv[argv.index("--max-wall-seconds") + 1] == "60"
    assert Path(argv[argv.index("--continue-from") + 1]).as_posix() == "/parent"


def test_harness2_launch_flags_spec_and_entry(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test")
    args = ["--framework", "harness2", "--harness", "opencode", "--model", "openrouter/qwen/qwen3.8-27b",
            "--effort", "low", "--optimizer-model", "openrouter/anthropic/claude-opus-4.8",
            "--optimizer-effort", "high", "--game-id", "ps_modality-v1", "--backend-url", "http://localhost:8000",
            "--output-dir", str(tmp_path / "run"), "--k", "1", "--recursion", "sequential", "--max-steps", "20",
            "--dry-run"]
    assert launch.launch(args) == 0
    config = json.loads(capsys.readouterr().out)["run_spec"]
    assert config["framework"] == "harness2" and config["options"] == {"k": 1, "recursion": "sequential", "max_steps": 20,
                                                                       "stop_after_levels": 0, "levels": 0,
                                                                       "budgets": "30,50,100,200,500",
                                                                       "skip_below_shortest": False, "max_rounds": 5}
    assert config["optimizer_model"] == "openrouter/anthropic/claude-opus-4.8" and config["optimizer_effort"] == "high"
    argv = HARNESS2.entry(config, True, Path("/results"), Path("/parent"))
    assert argv[0] == "frameworks.harness2.run" and argv[-1] == "--resume"
    assert argv[argv.index("--backend-url") + 1] == "http://host.docker.internal:8000"


def test_opencode_error_event_with_zero_exit_is_a_failed_turn(tmp_path, monkeypatch):
    from harnesses.opencode import OpenCodeSession

    def stream(command, *, on_line, **kwargs):
        on_line(json.dumps({"type": "error", "error": {"name": "APIError", "data": {"message": "Insufficient credits"}}}))
        return 0, False, ""

    monkeypatch.setattr("harnesses.base.run_streaming", stream)
    with OpenCodeSession().start(tmp_path / "ws", "S", "openrouter/qwen/qwen3.8-27b", "low",
                                 "player", tmp_path / "analysis") as session:
        result = session.turn("go")
    assert result.error == "Insufficient credits" and result.text == ""
    assert json.loads((tmp_path / "analysis/sent.jsonl").read_text())["instruction"] == "go"


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
    assert json.loads((tmp_path / "analysis/sent.jsonl").read_text())["instruction"] == "go"


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


@pytest.mark.parametrize("enabled,kept", [(False, ["frame.png", "scratch.py", "tmpdir"]),
                                          (True, [".act", "act.py", "frame.png", "notes", "scratch.py", "tmpdir"])])
def test_baseline_keeps_every_file_between_turns(tmp_path, monkeypatch, enabled, kept):
    from frameworks.baseline import session as module
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
    assert manifest["harness"] == "claude-code" and "nothing deleted" in manifest["workspace_policy"]


class ActingHarness(FakeHarness):
    """Submits the action with act.py instead of replying with JSON."""
    action = "ACTION3"

    def turn(self, instruction, images=(), timeout=None):
        import subprocess
        import sys
        self.turn_number += 1
        done = subprocess.run([sys.executable, "act.py", self.action, "--note", "why"], cwd=self.workspace,
                              capture_output=True, text=True)
        again = subprocess.run([sys.executable, "act.py", self.action], cwd=self.workspace,
                               capture_output=True, text=True)
        assert self.stop_check() and "Your turn ends now" in done.stdout and "already submitted" in again.stderr
        return TurnResult(text="", session_id="s", usage={}, events=[{"type": "command"}])


def test_baseline_act_py_submits_the_action(tmp_path, monkeypatch):
    import subprocess
    import sys
    from frameworks.baseline import session as module
    monkeypatch.setattr("harnesses.registry.create_session", lambda harness: ActingHarness())
    config = module.GameSessionConfig(model="claude-haiku-5-5", harness="claude-code", workspace_enabled=True)
    workspace = tmp_path / "ws"
    with module.CliGameSession(config, workspace, tmp_path / "out") as game:
        game.available_actions = ["ACTION3", "ACTION4"]
        assert game.next_action("p") == {"operation": "ACT", "action": "ACTION3", "note": "why"}
        assert not game.session.stop_check()  # nothing stays submitted between turns
        refused = subprocess.run([sys.executable, "act.py", "ACTION3"], cwd=workspace, capture_output=True, text=True)
        assert "No game turn is open" in refused.stderr
        ActingHarness.action = "ACTION1"
        try:
            with pytest.raises(AssertionError):
                game.next_action("p")  # not available this turn: act.py refuses, nothing submitted
        finally:
            ActingHarness.action = "ACTION3"


def test_run_streaming_stops_when_asked(tmp_path):
    import os
    import sys
    from harnesses.base import run_streaming
    lines = []
    code, timed_out, _ = run_streaming(
        [sys.executable, "-c", "import time\nfor i in range(50):\n print(i, flush=True); time.sleep(0.1)"],
        cwd=tmp_path, env=dict(os.environ), timeout=30, raw_path=tmp_path / "raw.jsonl",
        on_line=lines.append, should_stop=lambda line: line == "2")
    assert code == 0 and not timed_out and lines == ["0", "1", "2"]


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
    from frameworks.avo.client.turns import INNER_RUN_INSTRUCTION, AgentConfig, CliAgent
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
    from frameworks.avo.client.turns import AgentConfig, CliAgent

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


def test_baseline_driver_agent_runs_the_agent_player():
    spec = {"framework": "baseline", "harness": "opencode", "model": "nanogpt/qwen/qwen3.8-27b:thinking", "effort": "medium",
            "game_id": "ps_modality-v1", "backend_url": "http://host.docker.internal:8000", "provider": "",
            "max_wall_seconds": 0, "options": BASELINE.check_options({"driver": "agent", "max_steps": 50})}
    argv = BASELINE.entry(spec, False, Path("/results"), Path("/parent"))
    assert argv[0] == "frameworks.baseline.agent" and "--notes" not in argv and argv[argv.index("--max-steps") + 1] == "50"
    assert BASELINE.entry({**spec, "options": {**spec["options"], "driver": "controller"}}, False,
                          Path("/results"), Path("/parent"))[0] == "frameworks.baseline.run"
    assert BASELINE.variant_label(spec["options"]) == "Baseline · agent"
    assert BASELINE.variant_label({"driver": "agent", "notes": True}) == "Baseline · agent · notes"  # older runs
    with pytest.raises(ValueError, match="cannot be continued"):
        BASELINE.entry({**spec, "continued_from": "/runs/parent"}, False, Path("/results"), Path("/parent"))


def test_baseline_level_options_reach_both_drivers():
    spec = {"framework": "baseline", "harness": "opencode", "model": "m", "effort": "medium", "game_id": "ps_modality-v1",
            "backend_url": "http://host.docker.internal:8001", "provider": "", "max_wall_seconds": 0}
    for driver in ("agent", "controller"):
        options = BASELINE.check_options({"driver": driver, "start_level": 3, "one_level": True})
        argv = BASELINE.entry({**spec, "options": options}, False, Path("/results"), Path("/parent"))
        assert argv[argv.index("--start-level") + 1] == "3" and argv[argv.index("--stop-after-levels") + 1] == "1"
    plain = BASELINE.entry({**spec, "options": BASELINE.check_options({})}, False, Path("/results"), Path("/parent"))
    assert "--start-level" not in plain and "--stop-after-levels" not in plain
    assert BASELINE.variant_label({"driver": "agent", "start_level": 3, "one_level": True}) == "Baseline · agent · level 3"
    assert BASELINE.variant_label({"driver": "agent", "start_level": 3}) == "Baseline · agent · from level 3"
    assert BASELINE.variant_label({"driver": "agent", "start_level": 2, "stop_after_levels": 2}) ==         "Baseline · agent · levels 2-3"
    with pytest.raises(ValueError, match="one-level"):
        BASELINE.check_options({"one_level": True, "stop_after_levels": 2})
    with pytest.raises(ValueError, match="start-level"):
        BASELINE.check_options({"start_level": 0})
