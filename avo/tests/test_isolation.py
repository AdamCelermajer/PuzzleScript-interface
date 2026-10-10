import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from avo.analysis.request_guard import RequestGuard
from avo.analysis.model_proxy import CodexRequestProxy
from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.core.model_view import ModelView
from avo.isolation import IsolatedRuntime, IsolationError, REPOSITORY, assert_workspace, runtime_root, _new_private_directory


def test_repository_workspaces_are_rejected():
    with pytest.raises(IsolationError):
        assert_workspace(REPOSITORY / "avo" / "output")


def test_public_helper_reference_does_not_allow_private_files(tmp_path):
    private = tmp_path / 'private'
    helper = private / 'tmp' / 'arg0'
    RequestGuard(forbidden_roots=(private,), public_helper_root=helper).check(
        {'input': [{'role': 'user', 'content': f'<path>{helper}</path>'}]})
    aliases = helper / 'codex-arg07orX7y'
    for path in [private / 'auth.json', helper / '../../auth.json', helper / 'extra',
                 aliases / '../../auth.json', aliases / 'auth.json',
                 aliases / 'apply_patch' / '../../../auth.json',
                 aliases / 'apply_patch.extra', helper.parent]:
        with pytest.raises(IsolationError):
            RequestGuard(forbidden_roots=(private,), public_helper_root=helper).check(
                {'input': [{'role': 'user', 'content': str(path)}]})


def test_public_helper_directory_listings_are_allowed(tmp_path):
    private = tmp_path / 'private'
    helper = private / 'tmp' / 'arg0'
    aliases = helper / 'codex-arg07orX7y'
    listing = '\n'.join([
        f'{helper}:', f'{aliases}:',
        *(str(aliases / name) for name in
          ('apply_patch', 'applypatch', 'codex-execve-wrapper', 'codex-linux-sandbox', '.lock')),
        f'{aliases}/',
    ])
    # Captured tool output can itself be JSON with escaped Windows separators.
    guard = RequestGuard(forbidden_roots=(private,), public_helper_root=helper)
    guard.check({'input': [{'type': 'function_call_output', 'output': json.dumps({'output': listing})}]})
    assert guard.requests_checked == 1
    with pytest.raises(IsolationError, match='Framework/private path'):
        guard.check({'input': [{'type': 'function_call_output',
                                'output': listing + '\n' + str(private / 'auth.json')}]})


def test_private_path_matching_uses_path_boundaries(tmp_path):
    private = tmp_path / 'private'
    RequestGuard(forbidden_roots=(private,)).check(
        {'input': [{'role': 'user', 'content': str(tmp_path / 'private-other')}]})
    with pytest.raises(IsolationError):
        RequestGuard(forbidden_roots=(private,)).check(
            {'input': [{'role': 'user', 'content': f'File "{private / "secret"}"'}]})


def test_inherited_instruction_files_are_rejected(tmp_path):
    (tmp_path / "AGENTS.md").write_text("unexpected context")
    with pytest.raises(IsolationError):
        assert_workspace(tmp_path)


def test_empty_native_mount_points_are_allowed_but_contents_are_rejected(tmp_path):
    for name in ('.codex', '.agents'):
        (tmp_path / name).mkdir()
    assert_workspace(tmp_path)
    (tmp_path / '.codex' / 'config.toml').write_text('unapproved')
    with pytest.raises(IsolationError):
        assert_workspace(tmp_path)


def test_private_config_has_no_legacy_broad_read_override(tmp_path):
    runtime = IsolatedRuntime(tmp_path / "workspace", tmp_path / "artifacts", "codex")
    config = (runtime.private / "config.toml").read_text()
    assert 'default_permissions = "avo"' in config
    assert '":root" = "deny"' in config
    assert 'project_doc_max_bytes = 0' in config
    assert "sandbox_mode" not in config
    assert "sandbox_workspace_write" not in config
    assert runtime.env.get("PYTHONPATH", "") == ""
    assert runtime.env.get("OPENAI_API_KEY", "") == ""
    if os.name != "nt":
        assert runtime.env["HOME"] == str(runtime.workspace)
        assert runtime.env["CODEX_HOME"] == str(runtime.private)


def test_windows_setup_identity_is_preserved_but_secrets_are_cleared(tmp_path):
    with patch.dict(os.environ, {"USERNAME": "owner", "USERDOMAIN": "machine",
                                "OPENAI_API_KEY": "test-only-secret", "PYTHONPATH": "unrelated-code"}):
        runtime = IsolatedRuntime(tmp_path / "workspace", tmp_path / "artifacts", "codex")
    assert runtime.env["USERNAME"] == "owner"
    assert runtime.env["USERDOMAIN"] == "machine"
    assert runtime.env["OPENAI_API_KEY"] == ""
    assert runtime.env["PYTHONPATH"] == ""


def test_runtime_root_does_not_depend_on_virtualized_localappdata(tmp_path):
    with patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path / "package-cache")}):
        assert runtime_root() == (Path.home() / ".avo/isolated").resolve()


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL setup")
def test_new_runtime_acl_grants_only_the_callers_sid(tmp_path):
    sid = "S-1-5-21-1-2-3-1001"
    identity = subprocess.CompletedProcess([], 0, f'"machine\\owner","{sid}"', "")
    success = subprocess.CompletedProcess([], 0, "", "")
    with patch("avo.isolation.runtime_root", return_value=tmp_path), patch(
        "avo.isolation.subprocess.run", side_effect=[identity, success]
    ) as execute:
        directory = _new_private_directory("c-")
    acl_command = execute.call_args_list[1].args[0]
    assert acl_command[1:] == [str(directory), "/grant:r", f"*{sid}:(OI)(CI)F", "/q"]
    assert directory.parent == tmp_path.resolve()


def test_successful_command_with_leaky_permissions_is_rejected(tmp_path):
    runtime = IsolatedRuntime(tmp_path / "workspace", tmp_path / "artifacts", "codex")
    def leaky_probe(*args, **kwargs):
        (runtime.workspace / "_isolation_probe.json").write_text(json.dumps(
            {"python": True, "write": True, "readable": [False, True, True], "network": True}))
        return subprocess.CompletedProcess([], 0, "", "")
    with patch("avo.isolation.subprocess.run", side_effect=leaky_probe), pytest.raises(IsolationError):
        runtime.preflight()
    report = json.loads((runtime.artifacts / "isolation_preflight.json").read_text())
    assert report["return_code"] == 0
    assert report["passed"] is False


def test_failed_native_preflight_fails_closed(tmp_path):
    runtime = IsolatedRuntime(tmp_path / "workspace", tmp_path / "artifacts", "codex")
    result = subprocess.CompletedProcess([], 1, "", "unsupported restricted read policy")
    with patch("avo.isolation.subprocess.run", return_value=result), pytest.raises(IsolationError):
        runtime.preflight()
    assert json.loads((tmp_path / "artifacts/isolation_preflight.json").read_text())["passed"] is False


def test_request_guard_blocks_late_agents_injection():
    guard = RequestGuard(forbidden_roots=())
    guard.check({"input": []})
    with pytest.raises(IsolationError):
        guard.check({"input": [{"role": "user", "content": [{"text": "# AGENTS.md instructions for somewhere"}]}]})
    assert guard.requests_checked == 1
    with pytest.raises(IsolationError):
        guard.check({"input": []})


def test_request_guard_blocks_nested_escaped_framework_paths(tmp_path):
    guard = RequestGuard(forbidden_roots=(tmp_path,))
    output = str(tmp_path / "game-name" / "evidence.json")
    for _ in range(4):
        output = json.dumps({"nested": output})
    with pytest.raises(IsolationError):
        guard.check({"input": [{"type": "function_call_output", "output": output}]})


def test_guard_does_not_censor_model_guesses_or_learned_controls():
    guard = RequestGuard(forbidden_roots=())
    guard.check({"input": [{"role": "assistant", "content": "This looks like Midas. ACTION1=Up."},
                           {"type": "function_call_output", "output": "Saved note: Sokoban hypothesis; ACTION1=Up observed."}]})


def test_guard_blocks_canary_in_external_context():
    guard = RequestGuard(forbidden_roots=(), canaries=("UNRELATED_RUN_CANARY",))
    with pytest.raises(IsolationError):
        guard.check({"input": [{"role": "user", "content": "UNRELATED_RUN_CANARY"}]})


def test_guard_checks_nested_tool_inventory():
    guard = RequestGuard(forbidden_roots=())
    guard.check({"input": [{"type": "additional_tools", "tools": [{"type": "namespace", "name": "functions", "tools": [
        {"name": "exec_command"}, {"name": "get_goal"}, {"name": "create_goal"}, {"name": "update_goal"}]}]}]})
    assert guard.tools_seen == {"exec_command", "get_goal", "create_goal", "update_goal"}
    with pytest.raises(IsolationError):
        guard.check({"input": [], "tools": [{"name": "web_search"}]})


def test_native_tool_discovery_requires_explicit_client_side_opt_in():
    tool = {"type": "tool_search", "execution": "client"}
    with pytest.raises(IsolationError):
        RequestGuard(forbidden_roots=()).check({"input": [], "tools": [tool]})
    guard = RequestGuard(forbidden_roots=(), allowed_tools={"tool_search", "write_note"})
    guard.check({"input": [], "tools": [tool]})
    guard.check({"input": [{"type": "tool_search_output", "tools": [
        {"type": "namespace", "name": "codex_notes", "tools": [{"name": "write_note"}]}]}]})
    assert guard.tools_seen == {"tool_search", "write_note"}
    with pytest.raises(IsolationError):
        guard.check({"input": [{"type": "tool_search_output", "tools": [{"name": "exec_command"}]}]})
    with pytest.raises(IsolationError):
        RequestGuard(forbidden_roots=(), allowed_tools={"tool_search"}).check(
            {"input": [], "tools": [{"type": "tool_search", "execution": "server"}]})


def test_image_bytes_preserved_but_path_is_anonymous(tmp_path):
    archive = tmp_path / "midas-private-archive"
    archive.mkdir()
    image = archive / "midas.png"
    data = b"\x89PNG\r\n\x1a\nfixture"
    image.write_bytes(data)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    view = ModelView(workspace, (archive,))
    result = view.present({"metadata": {"game_id": "midas", "rendered_frame": {"path": str(image), "mime_type": "image/png"}}})
    assert "midas" not in json.dumps(result)
    assert Path(result["metadata"]["rendered_frame"]["path"]).read_bytes() == data
    assert image.read_bytes() == data


def test_view_hides_archive_metadata_without_mutating_record(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    view = ModelView(workspace, (tmp_path / "archive",))
    record = {"candidate": {"candidate_id": "x_0001", "path": str(tmp_path / "archive/x_0001")},
              "fitness": 3, "profile_settings": {"game_id": "midas"},
              "learned_notes": {"strategy.md": "I hypothesize Sokoban."}}
    result = view.present(record)
    assert result["candidate"] == {"candidate_id": "x_0001"}
    assert "profile_settings" not in result
    assert "profile_settings" in record
    assert result["learned_notes"] == record["learned_notes"]


def test_view_rejects_frame_outside_artifact_roots(tmp_path):
    view = ModelView(tmp_path / "workspace", (tmp_path / "archive",))
    with pytest.raises(IsolationError):
        view.present({"rendered_frame": {"path": str(tmp_path / "private.png")}})


def test_evaluation_score_is_preserved_while_archive_path_is_hidden(tmp_path):
    view = ModelView(tmp_path / "workspace", (tmp_path / "archive",))
    result = view.present({"evaluation": {"fitness": 2, "success": True,
                                         "output_dir": str(tmp_path / "archive"),
                                         "solver": str(tmp_path / "archive/solver")}})
    assert result == {"evaluation": {"fitness": 2, "success": True}}


def test_top_level_instructions_are_checked():
    guard = RequestGuard(forbidden_roots=())
    with pytest.raises(IsolationError):
        guard.check({"input": [], "instructions": "# AGENTS.md instructions for inherited context"})


def test_proxy_rejects_before_http_forwarding(tmp_path):
    # Port 9 is intentionally not an upstream model service. A 400 plus saved
    # rejection proves this request stopped at validation, before forwarding.
    proxy = CodexRequestProxy(tmp_path, session_id="test", session_role="test",
                              upstream_origin="http://127.0.0.1:9", guard=RequestGuard(forbidden_roots=()))
    proxy.start()
    try:
        request = urllib.request.Request(proxy.model_base_url + "/responses",
            data=json.dumps({"input": [{"role": "user", "content": "# AGENTS.md instructions for repo"}]}).encode(),
            headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        assert caught.value.code == 400
        record = json.loads(next(tmp_path.glob("request-*.json")).read_text())
        assert record["forwarding_allowed"] is False
        assert proxy.guard.failure
    finally:
        proxy.stop()


def test_capture_failure_latches_invalid_state(tmp_path):
    proxy = CodexRequestProxy(tmp_path, session_id="test", session_role="test",
                              guard=RequestGuard(forbidden_roots=()))
    with patch.object(Path, "write_text", side_effect=OSError("disk full")), pytest.raises(IsolationError):
        proxy._record_request("responses_http", b'{"input": []}')
    with pytest.raises(IsolationError):
        proxy.guard.check({"input": []})


def test_websocket_request_is_checked_and_unknown_messages_fail_closed(tmp_path):
    proxy = CodexRequestProxy(tmp_path, session_id="test", session_role="test",
                              guard=RequestGuard(forbidden_roots=()))
    proxy._record_request("responses_websocket", b'{"type":"response.create","input":[]}')
    with pytest.raises(IsolationError):
        proxy._record_request("responses_websocket", b'{"type":"unknown","input":[]}')


def test_normal_runs_do_not_require_a_separate_isolation_probe(tmp_path):
    agent = CodexOAuthAgent(CodexOAuthConfig(analysis_dir=tmp_path / "artifacts"))
    with patch("avo.client.codex_oauth_agent._find_codex_bin", return_value="codex"), patch.object(
        IsolatedRuntime, "preflight", side_effect=IsolationError("probe failed")
    ) as probe, patch.object(IsolatedRuntime, "authenticate") as auth, patch.object(agent, "_run") as run:
        agent.run(object(), tmp_path / "workspace")
        probe.assert_not_called()
        auth.assert_called_once()
        run.assert_called_once()


def test_preflight_timeout_is_infrastructure_failure(tmp_path):
    runtime = IsolatedRuntime(tmp_path / "workspace", tmp_path / "artifacts", "codex")
    with patch("avo.isolation.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 45)), pytest.raises(IsolationError):
        runtime.preflight()
    assert json.loads((tmp_path / "artifacts/isolation_preflight.json").read_text())["passed"] is False
