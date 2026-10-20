"""Unified harness run API (revamp contract §2-4), legacy normalization and ported Vite routes."""
import json
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench import harness_catalog
from workbench.catalog import snapshot
from workbench.experiment_job import batch_deadline, overdue, run_job
from workbench.experiments import create_router, write_json

LAUNCH = ["uv", "run", "python", "-m", "harnesses.launch"]
NO_DOCKER = ({}, None)


@pytest.fixture(autouse=True)
def no_docker_probe():
    # Liveness probes and readiness checks must not depend on the host's Docker.
    with patch("workbench.catalog.live_containers", return_value=NO_DOCKER), \
            patch("workbench.runs.live_containers", return_value=NO_DOCKER), \
            patch("workbench.harness_catalog.docker_objects",
                  return_value={"docker": True, "image": True, "agy_volume": False}):
        yield


def client(root, **kwargs):
    app = FastAPI()
    app.include_router(create_router(root, **kwargs))
    return TestClient(app)


def put(root: Path, name: str, value) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    return path.parent


def arg(command, flag):
    return command[command.index(flag) + 1]


# ---------------------------------------------------------------- /harnesses

def test_harness_listing_reports_readiness_without_secret_values(tmp_path, monkeypatch):
    secret = "sk-ant-oat-never-returned-123"
    (tmp_path / ".env").write_text(f"CLAUDE_CODE_OAUTH_TOKEN={secret}\nOPENROUTER_API_KEY=\n", encoding="utf-8")
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "OPENROUTER_API_KEY", "NANOGPT_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setitem(sys.modules, "harnesses.registry", None)  # import fails: package not ready
    with client(tmp_path) as api:
        response = api.get("/api/workbench/harnesses", params={"catalogs": "false"})
    assert response.status_code == 200
    assert secret not in response.text
    entries = {entry["id"]: entry for entry in response.json()}
    assert list(entries) == ["codex", "claude-code", "opencode", "antigravity", "bare"]
    for entry in entries.values():
        assert {"id", "label", "providers", "models", "efforts", "ready", "missing"} <= set(entry)
        assert entry["efforts"] == ["low", "medium", "high", "xhigh", "max"]
        assert entry["ready"] is False and "harnesses package" in entry["missing"]
    assert [m["id"] for m in entries["claude-code"]["models"]] == [
        "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]
    assert "gemini-3.8-flash-high" in [m["id"] for m in entries["antigravity"]["models"]]
    assert not any("CLAUDE_CODE_OAUTH_TOKEN" in m for m in entries["claude-code"]["missing"])
    assert any("auth.json" in m for m in entries["codex"]["missing"])
    assert any("puzzlescript-agy-home" in m for m in entries["antigravity"]["missing"])
    assert any("OPENROUTER_API_KEY" in m for m in entries["opencode"]["missing"])


def test_harness_listing_is_ready_with_registry_credentials_and_docker(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("CLAUDE_CODE_OAUTH_TOKEN=x\n", encoding="utf-8")
    registry = types.ModuleType("harnesses.registry")
    registry.HARNESSES = {"claude-code": {"id": "claude-code", "label": "Claude Code CLI"}}
    monkeypatch.setitem(sys.modules, "harnesses.registry", registry)
    with patch("workbench.harness_catalog.docker_objects", return_value={"docker": True, "image": True, "agy_volume": True}):
        entries = {e["id"]: e for e in harness_catalog.harness_listing(tmp_path, include_public_catalogs=False)}
    assert entries["claude-code"]["ready"] is True and entries["claude-code"]["label"] == "Claude Code CLI"
    assert "harnesses package" not in entries["antigravity"]["missing"]


def test_model_membership_follows_harness_provider():
    assert harness_catalog.model_error("codex", "gpt-5.6-sol") is None
    assert harness_catalog.model_error("claude-code", "claude-opus-5-5") is None
    assert harness_catalog.model_error("antigravity", "claude-opus-5-5-high") is None
    assert harness_catalog.model_error("opencode", "openrouter/qwen/qwen3.8-27b") is None
    assert harness_catalog.model_error("bare", "nanogpt/qwen/qwen3.8-flash") is None
    assert harness_catalog.model_error("codex", "openrouter/qwen/qwen3.8-27b")
    assert harness_catalog.model_error("claude-code", "claude-opus-5-5-high")
    assert harness_catalog.model_error("opencode", "gpt-5.6-sol")
    assert harness_catalog.model_error("opencode", "openrouter/no-vendor")


# ---------------------------------------------------------------- preview / matrix

MATRIX = {"frameworks": [{"id": "baseline"}, {"id": "baseline", "options": {"notes": True}},
                         {"id": "avo", "options": {"world_model_mode": "final-only"}},
                         {"id": "avo", "options": {"world_model_mode": "between-hypotheses"}}],
          "harnesses": ["codex", "claude-code"], "models": ["gpt-5.6-sol", "claude-sonnet-5-5"],
          "efforts": ["low", "high"], "games": ["ps_modality-v1"]}


def test_frameworks_endpoint_lists_the_registry(tmp_path):
    with client(tmp_path) as api:
        listing = {f["id"]: f for f in api.get("/api/workbench/frameworks").json()["frameworks"]}
    assert set(listing) == {"baseline", "avo", "harness2"}
    assert {o["name"] for o in listing["baseline"]["options"]} == {"max_steps", "notes"}
    assert listing["avo"]["optimizer"] is True and listing["baseline"]["optimizer"] is False


def test_preview_builds_matrix_with_contract_commands_and_never_starts(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKBENCH_BACKEND_URL", raising=False)
    with client(tmp_path) as api, patch("workbench.experiments.subprocess.Popen") as popen:
        response = api.post("/api/workbench/runs/preview", json=MATRIX)
        popen.assert_not_called()
    assert response.status_code == 200, response.text
    data = response.json()
    # Valid pairs: codex×gpt and claude-code×claude → 2 × 2 efforts × 4 framework choices.
    assert data["count"] == len(data["runs"]) == 16
    assert any("Skipped codex × claude-sonnet-5-5" in w for w in data["warnings"])
    for run in data["runs"]:
        command = run["command"]
        assert command[:5] == LAUNCH
        assert arg(command, "--framework") == run["framework"] and arg(command, "--harness") == run["harness"]
        assert arg(command, "--backend-url") == "http://host.docker.internal:8000"
        assert arg(command, "--max-wall-seconds") == "0"
        if run["framework"] == "avo":
            assert arg(command, "--optimizer-model") == run["model"]
            assert arg(command, "--world-model-mode") == run["options"]["world_model_mode"]
            assert "--max-steps" not in command and arg(command, "--max-evaluations") == "8"
        else:
            assert arg(command, "--max-steps") == "200" and ("--notes" in command) == run["options"]["notes"]
            assert "--max-evaluations" not in command and "--world-model-mode" not in command
        assert "--provider" not in command
    # Matched rows share a match id across frameworks, so baseline vs baseline+ vs AVO compare in one launch.
    matched = [r for r in data["runs"] if r["harness"] == "codex" and r["effort"] == "low"]
    assert {r["variant"] for r in matched} == {"Baseline", "Baseline+", "AVO"}
    assert len({r["match_id"] for r in matched}) == 1


def test_options_optimizer_and_provider_pin_reach_commands(tmp_path):
    body = {"frameworks": [{"id": "avo", "options": {"max_evaluations": 3, "research_moves": 50, "solver_moves": 60}}],
            "harnesses": ["opencode"], "models": ["openrouter/qwen/qwen3.8-27b"],
            "optimizer_model": "openrouter/deepseek/deepseek-v4.1-flash", "optimizer_effort": "max",
            "efforts": ["high"], "games": ["ps_modality-v1"], "provider": "chutes",
            "backend_url": "http://10.0.0.5:8000/", "max_wall_seconds": 3600}
    with client(tmp_path) as api:
        run = api.post("/api/workbench/runs/preview", json=body).json()["runs"][0]
    command = run["command"]
    assert arg(command, "--optimizer-model") == "openrouter/deepseek/deepseek-v4.1-flash"
    assert arg(command, "--optimizer-effort") == "max" and arg(command, "--effort") == "high"
    assert arg(command, "--provider") == "chutes" and arg(command, "--backend-url") == "http://10.0.0.5:8000"
    assert [arg(command, f) for f in ("--max-wall-seconds", "--max-evaluations", "--research-moves", "--solver-moves")] == \
        ["3600", "3", "50", "60"]


@pytest.mark.parametrize("change, status, message", [
    ({"frameworks": [{"id": "baseline", "options": {"world_model_mode": "between-hypotheses"}}]}, 400, "no option"),
    ({"optimizer_model": "gpt-5.6-sol"}, 400, "optimizer"),
    ({"frameworks": [{"id": "baseline", "options": {"max_steps": 0}}]}, 400, "--max-steps"),
    ({"frameworks": [{"id": "avo", "options": {"world_model_mode": "never"}}]}, 400, "--world-model-mode"),
    ({"provider": "chutes"}, 400, "opencode and bare"),
    ({"harnesses": ["bare"], "models": ["nanogpt/qwen/x"], "provider": "chutes"}, 400, "OpenRouter"),
    ({"harnesses": ["codex"], "models": ["claude-opus-5-5"]}, 400, "anthropic"),
    ({"harnesses": ["codex", "opencode"], "models": ["claude-opus-5-5"]}, 400, "No selected harness"),
    ({"games": [f"g{i}" for i in range(30)], "repeats": 5}, 400, "at most 120"),
    ({"frameworks": [{"id": "nope"}]}, 422, None),
    ({"kind": "avo"}, 422, None),
    ({"max_wall_seconds": -1}, 422, None),
    ({"efforts": ["minimal"]}, 422, None),
    ({"harnesses": ["tools"]}, 422, None),
])
def test_request_validation(tmp_path, change, status, message):
    body = {"frameworks": [{"id": "baseline"}], "harnesses": ["codex"], "models": ["gpt-5.6-sol"],
            "games": ["ps_modality-v1"], **change}
    with client(tmp_path) as api, patch("workbench.experiments.subprocess.Popen") as popen:
        for endpoint in ("/runs/preview", "/runs"):
            response = api.post("/api/workbench" + endpoint, json=body)
            assert response.status_code == status, response.text
            if message:
                assert message in response.json()["detail"]
        popen.assert_not_called()


def test_enqueue_is_routed_to_its_dedicated_backend_in_a_mixed_matrix(tmp_path):
    body = {"frameworks": [{"id": "baseline"}], "harnesses": ["codex"], "models": ["gpt-5.6-sol"],
            "games": ["ps_enqueue-v1", "ps_modality-v1"]}
    with client(tmp_path) as api:
        data = api.post("/api/workbench/runs/preview", json=body).json()
    urls = {r["game_id"]: arg(r["command"], "--backend-url") for r in data["runs"]}
    assert urls == {"ps_enqueue-v1": "http://host.docker.internal:8001", "ps_modality-v1": "http://host.docker.internal:8000"}
    assert any("start-enqueue-backend.ps1" in w for w in data["warnings"])


def test_backend_url_default_comes_from_one_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKBENCH_BACKEND_URL", "http://arc.local:9000")
    body = {"frameworks": [{"id": "baseline"}], "harnesses": ["codex"], "models": ["gpt-5.6-sol"], "games": ["g"]}
    with client(tmp_path) as api:
        run = api.post("/api/workbench/runs/preview", json=body).json()["runs"][0]
    assert arg(run["command"], "--backend-url") == "http://arc.local:9000"


# ---------------------------------------------------------------- launch

def test_launch_writes_matrix_manifest_and_detaches_one_worker(tmp_path):
    body = {**MATRIX, "label": "Qwen modality", "parallel": 3}
    with client(tmp_path) as api, patch("workbench.experiments.subprocess.Popen") as popen:
        response = api.post("/api/workbench/runs", json=body)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert "qwen-modality" in job_id
    popen.assert_called_once()
    assert popen.call_args.args[0][1:] == ["-m", "workbench.experiment_job", str(tmp_path / job_id)]
    manifest = json.loads((tmp_path / job_id / "job.json").read_text())
    assert manifest["config"]["kind"] == "matrix" and manifest["config"]["parallel"] == 3
    assert len(manifest["runs"]) == 16
    campaign = next(r for r in manifest["runs"] if r["framework"] == "avo")
    assert campaign["id"].endswith("/campaign") and campaign["launcher"] == "harnesses"
    # The catalog shows queued rows with normalized identity before artifacts exist.
    rows = {r["id"]: r for r in snapshot(tmp_path, {})["runs"]}
    assert rows[campaign["id"]]["framework"] == "avo" and rows[campaign["id"]]["harness"] == campaign["harness"]
    assert rows[campaign["id"]]["variant"] == "AVO"


def test_post_runs_without_frameworks_still_serves_rule_agent_start(tmp_path):
    seen = []
    with client(tmp_path, legacy_start=lambda payload: seen.append(payload) or {"run_id": "legacy"}) as api:
        response = api.post("/api/workbench/runs", json={"agent_mode": "rule", "game_id": "g"})
    assert response.status_code == 202 and response.json() == {"run_id": "legacy"}
    assert seen == [{"agent_mode": "rule", "game_id": "g"}]


# ---------------------------------------------------------------- worker budgets

def test_unlimited_wall_harness_batch_has_no_deadline_and_completes(tmp_path):
    assert batch_deadline({"budget": {"max_wall_seconds": 0}}, 100.0) is None
    assert batch_deadline({"launcher": "harnesses", "budget": {"max_wall_seconds": 60}}, 100.0) is None
    assert batch_deadline({"max_hours": 1}, 100.0) == 100.0 + 3600 + 600
    assert batch_deadline({"max_hours": 0}, 100.0) is None
    marker = tmp_path / "finished"
    command = [sys.executable, "-c", f"import time; from pathlib import Path; time.sleep(.1); Path({str(marker)!r}).touch()"]
    write_json(tmp_path / "job.json", {"config": {"kind": "matrix", "launcher": "harnesses", "parallel": 1,
                                                  "budget": {"max_wall_seconds": 0}},
                                       "runs": [{"launcher": "harnesses", "harness": "claude-code", "kind": "codex",
                                                 "max_wall_seconds": 0, "output": str(tmp_path / "run-0001"),
                                                 "command": command, "status": "queued"}]})
    with patch("workbench.experiment_job.time.time", side_effect=range(1000, 10_000_000, 100_000)):
        run_job(tmp_path)
    assert marker.exists()
    assert json.loads((tmp_path / "job.json").read_text())["status"] == "completed"


def test_overdue_child_is_backstopped_only_with_a_finite_wall():
    row = {"launcher": "harnesses", "max_wall_seconds": 60, "started_at": 0}
    assert overdue(row, 60 + 599) is False and overdue(row, 60 + 600) is True
    assert overdue({**row, "max_wall_seconds": 0}, 10**9) is False
    assert overdue({**row, "launcher": None}, 10**9) is False


def test_worker_rejects_unknown_harness_rows(tmp_path):
    write_json(tmp_path / "job.json", {"config": {"parallel": 1, "budget": {}}, "runs": [
        {"launcher": "harnesses", "harness": "raw", "kind": "codex", "output": str(tmp_path / "r"),
         "command": ["x"], "status": "queued"}]})
    with patch("workbench.experiment_job.subprocess.Popen") as start:
        run_job(tmp_path)
        start.assert_not_called()
    assert "unknown harness" in json.loads((tmp_path / "job.json").read_text())["error"]


# ---------------------------------------------------------------- resume

def spec(**values):
    return {"schema": "run-spec-v1", "created_at": "2026-10-15T09:00:00Z", **values}


def test_resume_baseline_continues_parent_into_new_directory_once(tmp_path):
    run = "output/workbench/job-a/run-0001"
    put(tmp_path, run + "/run_spec.json", spec(mode="baseline-plus", harness="claude-code", model="claude-sonnet-5-5",
                                              effort="high", game_id="ps_modality-v1",
                                              backend_url="http://host.docker.internal:8000",
                                              budget={"max_wall_seconds": 0, "max_steps": 300}))
    put(tmp_path, run + "/result.json", {"solved": False, "reason": "step_budget_exhausted"})
    with client(tmp_path) as api, patch("workbench.experiments.subprocess.Popen") as popen:
        response = api.post("/api/workbench/runs/resume", json={"run_id": run})
        assert response.status_code == 202, response.text
        assert api.post("/api/workbench/runs/resume", json={"run_id": run}).status_code == 409
    popen.assert_called_once()
    job = json.loads((tmp_path / response.json()["job_id"] / "job.json").read_text())
    command = job["runs"][0]["command"]
    assert command[:5] == LAUNCH and arg(command, "--framework") == "baseline" and "--notes" in command
    assert arg(command, "--continue-from") == str(tmp_path / run)
    assert arg(command, "--output-dir") != str(tmp_path / run) and arg(command, "--max-steps") == "300"
    assert job["recovery_of"] == run


def test_resume_campaign_copies_lineage_and_passes_resume(tmp_path):
    run = "output/workbench/job-b/run-0001/campaign"
    put(tmp_path, "output/workbench/job-b/run-0001/run_spec.json", spec(
        mode="campaign", harness="opencode", model="openrouter/qwen/qwen3.8-27b",
        optimizer_model="openrouter/qwen/qwen3.8-27b", effort="high", optimizer_effort="low", game_id="ps_modality-v1",
        backend_url="http://host.docker.internal:8000", world_model_mode="between-hypotheses", provider="chutes",
        budget={"max_wall_seconds": 0, "max_evaluations": 4, "research_moves": 100, "solver_moves": 200}))
    put(tmp_path, run + "/evolution_config.json", {"max_evaluations": 4, "world_model_mode": "between-hypotheses",
                                                   "profile_settings": {"game_id": "ps_modality-v1"}})
    put(tmp_path, run + "/lineage.json", {"candidates": [{"candidate_id": "x_0001"}], "evaluations": []})
    with client(tmp_path) as api, patch("workbench.experiments.subprocess.Popen"):
        response = api.post("/api/workbench/runs/resume", json={"run_id": run})
    assert response.status_code == 202, response.text
    command = json.loads((tmp_path / response.json()["job_id"] / "job.json").read_text())["runs"][0]["command"]
    assert "--resume" in command and "--continue-from" not in command
    assert arg(command, "--world-model-mode") == "between-hypotheses" and arg(command, "--provider") == "chutes"
    assert (tmp_path / response.json()["run_id"] / "lineage.json").is_file()
    assert json.loads((tmp_path / "output/workbench/job-b/run-0001/recovery.json").read_text())["resumed_as"] == response.json()["run_id"]


def test_resume_rejects_legacy_harnesses_solved_and_active_runs(tmp_path):
    put(tmp_path, "output/raw/run_config.json", {"condition": "baseline", "harness": "raw", "model": "openrouter/a/b",
                                                 "game_id": "g", "reasoning_effort": "low"})
    put(tmp_path, "output/solved/run_config.json", {"condition": "baseline", "model": "gpt-5.6-sol", "game_id": "g"})
    put(tmp_path, "output/solved/result.json", {"solved": True})
    active = "output/workbench/live/run-0001"
    put(tmp_path, active + "/run_config.json", {"condition": "baseline", "model": "gpt-5.6-sol", "game_id": "g"})
    import time
    put(tmp_path, "output/workbench/live/job.json", {"heartbeat": time.time(), "status": "running",
                                                       "runs": [{"id": active, "status": "running"}]})
    with client(tmp_path) as api, patch("workbench.experiments.subprocess.Popen") as popen:
        assert api.post("/api/workbench/runs/resume", json={"run_id": "output/raw"}).status_code == 409
        assert api.post("/api/workbench/runs/resume", json={"run_id": "output/solved"}).status_code == 400
        assert api.post("/api/workbench/runs/resume", json={"run_id": active}).status_code == 409
        assert api.post("/api/workbench/runs/resume", json={"run_id": "output/../x"}).status_code == 400
        popen.assert_not_called()


# ---------------------------------------------------------------- catalog normalization

def test_catalog_normalizes_legacy_and_run_spec_runs(tmp_path):
    put(tmp_path, "output/tools/run_config.json", {"condition": "baseline-plus-plus", "harness": "tools",
                                                   "model": "openrouter/a/b", "reasoning_effort": "max", "game_id": "g",
                                                   "max_steps": 50})
    put(tmp_path, "output/raw/run_config.json", {"condition": "baseline", "harness": "raw", "model": "openrouter/a/b"})
    put(tmp_path, "output/codex/run_config.json", {"condition": "baseline", "model": "gpt-5.5"})
    put(tmp_path, "output/old/campaign/evolution_config.json", {"agent_backend": "opencode", "player": {"model": "m", "effort": "low"},
                                                                "profile_settings": {"game_id": "g"}, "max_evaluations": 3})
    put(tmp_path, "output/new/run-0001/run_spec.json", spec(mode="baseline", harness="antigravity",
                                                            model="gemini-3.8-flash-high", game_id="g2", effort="high",
                                                            budget={"max_wall_seconds": 0, "max_steps": 9}))
    put(tmp_path, "output/new/run-0002/run_spec.json", spec(mode="campaign", harness="claude-code", model="claude-opus-5-5",
                                                            game_id="g3", effort="max", world_model_mode="final-only"))
    put(tmp_path, "output/new/run-0002/campaign/evolution_config.json", {"profile_settings": {"game_id": "g3"}})
    v2 = {"schema": "run-spec-v2", "harness": "opencode", "model": "openrouter/a/b", "effort": "low", "game_id": "g4",
          "max_wall_seconds": 60}
    put(tmp_path, "output/new/run-0003/run_spec.json", {**v2, "framework": "baseline", "options": {"max_steps": 7, "notes": True}})
    put(tmp_path, "output/new/run-0004/run_spec.json", {**v2, "framework": "avo",
                                                         "options": {"world_model_mode": "between-hypotheses"}})
    put(tmp_path, "output/new/run-0004/campaign/evolution_config.json", {"profile_settings": {"game_id": "g4"}})
    rows = {r["id"]: r for r in snapshot(tmp_path, {})["runs"]}
    assert (rows["output/tools"]["variant"], rows["output/tools"]["harness"], rows["output/tools"]["effort"]) == ("Baseline+", "bare", "max")
    assert rows["output/raw"]["harness"] == "bare-raw (legacy)" and rows["output/raw"]["resumable"] is False
    assert (rows["output/codex"]["framework"], rows["output/codex"]["variant"], rows["output/codex"]["harness"]) == \
        ("baseline", "Baseline", "codex")
    old = rows["output/old/campaign"]
    assert (old["framework"], old["harness"], old["spec_source"]) == ("avo", "opencode (legacy)", "legacy")
    new = rows["output/new/run-0001"]  # discovered from run_spec.json alone
    assert (new["framework"], new["harness"], new["model"], new["game_id"], new["budget"]) == \
        ("baseline", "antigravity", "gemini-3.8-flash-high", "g2", 9)
    assert new["spec_source"] == "run_spec" and new["agent_backend"] == "antigravity"
    campaign = rows["output/new/run-0002/campaign"]
    assert (campaign["framework"], campaign["harness"], campaign["effort"]) == ("avo", "claude-code", "max")
    assert "output/new/run-0002" not in rows
    v2 = rows["output/new/run-0003"]  # run-spec-v2 names the framework and its options
    assert (v2["framework"], v2["variant"], v2["options"], v2["max_wall_seconds"]) == \
        ("baseline", "Baseline+", {"max_steps": 7, "notes": True}, 60)
    assert (rows["output/new/run-0004/campaign"]["framework"], rows["output/new/run-0004/campaign"]["world_model_mode"]) == \
        ("avo", "between-hypotheses")
    assert "output/new/run-0004" not in rows


def test_record_exposes_agent_events_when_present_and_legacy_otherwise(tmp_path):
    put(tmp_path, "output/legacy/run_config.json", {"condition": "baseline", "model": "gpt-5.5"})
    run = put(tmp_path, "output/new/run_spec.json", spec(mode="baseline-plus", harness="codex", model="gpt-5.6-sol", game_id="g"))
    events = [{"schema": "agent-event-v1", "t": "2026-10-15T09:00:00Z", "role": "player", "turn": 1, "type": "command",
               "text": "ls", "output": "x" * 20000, "exit_code": 0, "harness": "codex", "secret_extra": "dropped"},
              {"t": "2026-10-15T09:00:01Z", "role": "player", "turn": 1, "type": "turn_end", "harness": "codex"}]
    (run / "agent_events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\nnot json\n", encoding="utf-8")
    put(tmp_path, "output/new/workspace/notes/plan.md", "# plan")
    with client(tmp_path) as api:
        legacy = api.get("/api/workbench/record", params={"run": "output/legacy"}).json()
        record = api.get("/api/workbench/record", params={"run": "output/new", "events_limit": 1}).json()
        file = api.get("/api/workbench/record/file", params={"run": "output/new", "file": "agent_events.jsonl"})
        note = api.get("/api/workbench/record/file", params={"run": "output/new", "file": "workspace/notes/plan.md"})
    assert legacy["agent_events"] is None and legacy["normalized"]["framework"] == "baseline"
    assert record["run_spec"]["harness"] == "codex" and record["normalized"]["spec_source"] == "run_spec"
    assert record["agent_events"]["total"] == 2 and record["agent_events"]["invalid_lines"] == 1
    assert record["agent_events"]["truncated"] is True and record["agent_events"]["events"][0]["type"] == "turn_end"
    assert record["agent_events"]["events"][0]["schema"] == "agent-event-v1"
    assert "agent_events.jsonl" in record["files"] and "workspace/notes/plan.md" in record["files"]
    assert file.status_code == 200 and note.status_code == 200
    with client(tmp_path) as api:
        full = api.get("/api/workbench/record", params={"run": "output/new"}).json()["agent_events"]["events"][0]
    assert "secret_extra" not in full and full["output"].endswith("[truncated]") and len(full["output"]) < 16100


# ---------------------------------------------------------------- ported Vite routes

def campaign_fixture(root: Path) -> str:
    run = "output/avo-test/campaign"
    put(root, run + "/evolution_config.json", {"profile_settings": {"game_id": "ps_sokoban_basic-v1"},
                                               "player": {"model": "gpt-5.6-sol", "max_environment_steps": 30},
                                               "optimizer_model": "gpt-6-astra", "max_evaluations": 2,
                                               "fresh_solver_max_environment_steps": 40})
    put(root, run + "/lineage.json", {"candidates": [{"candidate_id": "x_0001"}],
                                      "evaluations": [{"candidate_id": "x_0001", "fitness": 1, "success": False,
                                                       "score": {"win_levels": 3}}]})
    evidence = [{"type": "episode_started", "sequence": 1, "recorded_at": "2026-10-15T09:00:00Z",
                 "payload": {"observation": {"status": "PLAYING", "payload": {"frame": [[[0]]]}}}},
                {"type": "transition", "sequence": 2, "recorded_at": "2026-10-15T09:00:05Z",
                 "payload": {"action": {"id": "ACTION4"}, "after": {"status": "PLAYING",
                             "progress": {"levels_completed": 1, "win_levels": 3}, "payload": {"frame": [[[1]]]}}}}]
    put(root, run + "/x_0001/research/evidence.jsonl", "\n".join(map(json.dumps, evidence)) + "\n")
    put(root, run + "/x_0001/research/analysis/conversation.jsonl", "\n".join(map(json.dumps, [
        {"type": "reasoning", "role": "assistant_reasoning", "recorded_at": "2026-10-15T09:00:03Z", "turn": 1,
         "item": {"content": "Push right"}},
        {"type": "commandExecution", "role": "tool", "recorded_at": "2026-10-15T09:00:04Z",
         "item": {"command": "python avo_tool.py act ACTION4", "aggregatedOutput": "ok", "exitCode": 0}}])) + "\n")
    put(root, run + "/x_0001/STRATEGY.md", "# strategy")
    put(root, run + "/x_0001/research/model_requests/request-1.json", {"secret": "hidden"})
    put(root, run + "/optimizer_analysis/agent_events.jsonl", json.dumps(
        {"schema": "agent-event-v1", "t": "2026-10-15T09:00:00Z", "role": "optimizer", "turn": 1, "type": "message",
         "text": "Registering x_0001", "harness": "claude-code"}) + "\n")
    return run


def test_avo_snapshot_runs_logs_and_artifacts(tmp_path):
    run = campaign_fixture(tmp_path)
    with client(tmp_path) as api:
        runs = api.get("/api/workbench/avo/runs").json()["runs"]
        snap = api.get("/api/workbench/avo/run", params={"run": run}).json()
        logs = api.get("/api/workbench/avo/logs", params={"run": run, "scope": "x_0001", "stream": "all"}).json()
        outer = api.get("/api/workbench/avo/logs", params={"run": run, "scope": "outer"}).json()
        artifacts = api.get("/api/workbench/avo/artifacts", params={"run": run}).json()["artifacts"]
        artifact = api.get("/api/workbench/avo/artifact", params={"run": run, "path": "x_0001/STRATEGY.md"}).json()
        bad = [api.get("/api/workbench/avo/artifact", params={"run": run, "path": p}).status_code
               for p in ("../../../.env", "%2e%2e/%2e%2e/x.json", "x_0001/research/model_requests/request-1.json", "x.exe")]
        invalid = api.get("/api/workbench/avo/run", params={"run": "output/../avo-test/campaign"})
        missing = api.get("/api/workbench/avo/run", params={"run": "nope"})
    assert [r["run_id"] for r in runs] == [run]
    assert snap["phase"] == "research" and snap["current"] == "x_0001" and snap["win_levels"] == 3
    assert snap["research"]["actions"] == 1 and snap["frame_sessions"][0]["phase"] == "research"
    assert snap["candidates"][0]["research"]["fallback_frame"] == [[[1]]]
    titles = {e["title"] for e in logs["entries"]}
    assert {"Model reasoning", "avo_tool · act", "ACTION4 → PLAYING"} <= titles
    assert outer["entries"][0]["body"] == "Registering x_0001" and outer["entries"][0]["category"] == "conversation"
    paths = {a["path"] for a in artifacts}
    assert "x_0001/STRATEGY.md" in paths and not any("model_requests" in p for p in paths)
    assert artifact == {"path": "x_0001/STRATEGY.md", "size": 10, "truncated": False, "content": "# strategy"}
    assert bad == [403, 403, 403, 403]
    assert invalid.status_code == 400 and "error" in invalid.json()
    assert missing.status_code == 400


def test_avo_frame_replays_stored_grid_and_png_without_live_game(tmp_path):
    run = campaign_fixture(tmp_path)
    with client(tmp_path) as api:
        initial = api.get("/api/workbench/avo/frame", params={"run": run, "candidate": "x_0001", "phase": "research", "step": "0"}).json()
        first = api.get("/api/workbench/avo/frame", params={"run": run, "candidate": "x_0001", "phase": "research", "step": "1"}).json()
        outside = api.get("/api/workbench/avo/frame", params={"run": run, "candidate": "x_0001", "phase": "research", "step": "2"})
        unsafe = api.get("/api/workbench/avo/frame", params={"run": run, "candidate": "../x", "phase": "research"})
    assert initial["source"] == "stored_observation_grid" and initial["fallback_frame"] == [[[0]]]
    assert initial["reasoning"] == {"status": "initial"}
    assert first["fallback_frame"] == [[[1]]] and first["reasoning"]["text"] == "Push right"
    assert outside.status_code == 400 and unsafe.status_code == 400
    png = b"\x89PNG\r\n\x1a\nimage"
    phase = tmp_path / run / "x_0001/research"
    (phase / "frames").mkdir()
    (phase / "frames/1.png").write_bytes(png)
    lines = (phase / "evidence.jsonl").read_text().splitlines()
    event = json.loads(lines[1])
    event["payload"]["after"]["metadata"] = {"rendered_frame": {"artifact_path": "frames/1.png", "width": 5, "height": 6}}
    (phase / "evidence.jsonl").write_text(lines[0] + "\n" + json.dumps(event) + "\n")
    with client(tmp_path) as api:
        stored = api.get("/api/workbench/avo/frame", params={"run": run, "candidate": "x_0001", "phase": "research"}).json()
    assert stored["source"] == "stored_observation_png" and stored["rendered_frame"]["width"] == 5
    assert stored["rendered_frame"]["data_url"].startswith("data:image/png;base64,")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for isolated replay")
def test_avo_live_frame_uses_isolated_node_replay(tmp_path):
    from workbench.avo_console import ReplayWorker
    run = campaign_fixture(tmp_path)
    phase = tmp_path / run / "x_0001/research"
    worker = ReplayWorker(Path(__file__).resolve().parents[2])
    try:
        grid = worker.replay("ps_sokoban_basic-v1", "probe", phase / "evidence.jsonl")["frame"]
    finally:
        worker.close()
    lines = [json.loads(line) for line in (phase / "evidence.jsonl").read_text().splitlines()]
    lines[1]["payload"]["after"]["payload"]["frame"] = grid
    (phase / "evidence.jsonl").write_text("\n".join(map(json.dumps, lines)) + "\n")
    with client(tmp_path) as api:
        frame = api.get("/api/workbench/avo/frame", params={"run": run, "candidate": "x_0001", "phase": "research"}).json()
    assert frame["source"] == "isolated_runtime_replay" and frame["replay_exact"] is True
    assert frame["rendered_frame"] and frame["step"] == 1


def test_notes_and_pseudocode_saves_are_allowlisted(tmp_path):
    put(tmp_path, "docs/notes/todo.md", "old")
    put(tmp_path, "docs/pseudocode/manifest.json", [{"file": "entrypoint.md"}])
    with client(tmp_path) as api:
        saved = api.post("/api/workbench/notes", json={"file": "todo.md", "markdown": "a\nb\n"})
        denied = api.post("/api/workbench/notes", json={"file": "../secret.md", "markdown": "x"})
        missing = api.post("/api/workbench/notes", json={"file": "todo.md"})
        broken = api.post("/api/workbench/notes", content=b"{not json", headers={"Content-Type": "application/json"})
        large = api.post("/api/workbench/notes", json={"file": "todo.md", "markdown": "x" * (1024 * 1024 + 1)})
        code = api.post("/api/workbench/pseudocode", json={"file": "entrypoint.md", "markdown": "# entry"})
        unlisted = api.post("/api/workbench/pseudocode", json={"file": "other.md", "markdown": "# x"})
    assert saved.status_code == 200 and saved.json() == {"saved": True}
    assert (tmp_path / "docs/notes/todo.md").read_bytes() == b"a\nb\n"  # no newline translation
    assert (denied.status_code, missing.status_code, broken.status_code, large.status_code) == (403, 400, 400, 413)
    assert denied.json()["error"].startswith("Only notebook files")
    assert code.json() == {"saved": True, "file": "entrypoint.md"}
    assert (tmp_path / "docs/pseudocode/entrypoint.md").read_text() == "# entry"
    assert unlisted.status_code == 403


def test_harness2_record_lists_rollouts_and_catalog_keeps_the_optimizer(tmp_path):
    run = "output/workbench/20261020T104612-abc/run-0001"
    put(tmp_path, f"{run}/run_spec.json", {"schema": "run-spec-v2", "framework": "harness2", "options": {"k": 1},
                                           "harness": "opencode", "model": "nanogpt/qwen/qwen3.8-flash", "effort": "medium",
                                           "optimizer_model": "openrouter/anthropic/claude-opus-4.8", "optimizer_effort": "high",
                                           "game_id": "ps_modality-v1", "max_wall_seconds": 0})
    put(tmp_path, f"{run}/rollouts/base1/run_config.json", {"model": "nanogpt/qwen/qwen3.8-flash"})
    put(tmp_path, f"{run}/rollouts/base1/result.json", {"status": "completed", "levels_completed": 1, "action_count": 40})
    with client(tmp_path) as api:
        record = api.get("/api/workbench/record", params={"run": run}).json()
        row = next(r for r in api.get("/api/workbench/catalog").json()["runs"] if r["id"] == run)
    assert [r["label"] for r in record["rollouts"]] == ["base1"]
    assert record["rollouts"][0]["result"]["levels_completed"] == 1 and record["adoption"] is None
    assert row["optimizer_model"] == "openrouter/anthropic/claude-opus-4.8"
    assert row["rollouts"] == {"done": 1, "total": 5, "current": None, "current_actions": None}


def test_archive_moves_runs_without_touching_their_files(tmp_path):
    run = "output/workbench/20261020T104612-abc/run-0001"
    put(tmp_path, f"{run}/run_spec.json", {"schema": "run-spec-v2", "framework": "baseline", "options": {"max_steps": 5},
                                           "harness": "opencode", "model": "nanogpt/qwen/qwen3.8-flash", "effort": "low",
                                           "game_id": "ps_modality-v1", "max_wall_seconds": 0})
    put(tmp_path, f"{run}/run_config.json", {"model": "nanogpt/qwen/qwen3.8-flash", "game_id": "ps_modality-v1"})
    archived = lambda api: next(r for r in api.get("/api/workbench/catalog").json()["runs"] if r["id"] == run)["archived"]
    with client(tmp_path) as api:
        assert archived(api) is False
        assert api.post("/api/workbench/runs/archive", json={"runs": [run]}).json() == {"archived": [run]}
        assert archived(api) is True and (tmp_path / run / "run_spec.json").is_file()
        assert api.post("/api/workbench/runs/archive", json={"runs": [run], "archived": False}).json() == {"archived": []}
        assert archived(api) is False
        assert api.post("/api/workbench/runs/archive", json={"runs": ["../../etc"]}).status_code == 400
        assert api.post("/api/workbench/runs/archive", json={"runs": []}).status_code == 400
