import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from harnesses import launch
from harnesses.model_provider import VAST_BASE_URL
from workbench.runs import RunRequest, plan_matrix

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vast_campaign", ROOT / "scripts" / "vast" / "campaign.py")
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def planned(tmp_path, **kwargs):
    rows, warnings = plan_matrix(RunRequest.model_validate(campaign.batch_request(**kwargs)), tmp_path / "job", tmp_path)
    assert warnings == []
    return rows


def test_the_batch_is_each_game_with_both_drivers_all_at_once(tmp_path):
    rows = planned(tmp_path)
    assert Counter((r["game_id"], r["options"]["driver"]) for r in rows) == {
        (game, driver): 1 for game in campaign.GAMES for driver in ("agent", "controller")}
    assert campaign.batch_request()["parallel"] == 6
    assert {r["model"] for r in rows} == {"vast/q3.8-27b-fp8"} and {r["effort"] for r in rows} == {"xhigh"}
    assert {r["options"]["max_steps"] for r in rows} == {800}
    assert {r["options"]["turn_timeout"] for r in rows if r["options"]["driver"] == "controller"} == {campaign.TURN_TIMEOUT}


@pytest.mark.parametrize("driver", ["agent", "controller"])
def test_each_run_starts_and_reaches_the_tunnel_by_default(tmp_path, capsys, monkeypatch, driver):
    monkeypatch.delenv("VAST_LLM_BASE_URL", raising=False)
    row = next(r for r in planned(tmp_path) if r["options"]["driver"] == driver)
    assert row["command"][:5] == ["uv", "run", "python", "-m", "harnesses.launch"]
    assert launch.launch([*row["command"][5:], "--dry-run"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["run_spec"]["model"] == "vast/q3.8-27b-fp8"
    assert printed["run_spec"]["options"]["max_steps"] == 800
    assert "VAST_LLM_BASE_URL" in printed["command"]  # passed on when set; the harness's default is the tunnel
    assert VAST_BASE_URL == f"http://host.docker.internal:{campaign.LOCAL_PORT}/v1"


def test_the_server_is_the_21_oct_setup_with_mtp_on_all_four_gpus():
    script = (ROOT / "scripts" / "vast" / "setup_server.sh").read_text(encoding="utf-8")
    assert script.count("vllm serve") == 1 and "CUDA_VISIBLE_DEVICES" not in script
    for flag in ('"num_speculative_tokens":2', "--tensor-parallel-size 4", "--kv-cache-dtype fp8", "--max-model-len 262144",
                 "--enable-prefix-caching", '"reasoning_effort": "xhigh"'):
        assert flag in script


def test_the_batch_has_ended_only_in_a_final_state():
    assert not campaign.job_ended({"status": "starting"}) and not campaign.job_ended({"status": "running"})
    assert all(campaign.job_ended({"status": s}) for s in ("completed", "failed", "cancelled", "paused"))


def test_ssh_prefers_the_direct_port():
    info = {"public_ipaddr": "1.2.3.4 ", "ports": {"22/tcp": [{"HostPort": "4242"}]}, "ssh_host": "proxy", "ssh_port": 1}
    assert campaign.ssh_address(info) == ("1.2.3.4", 4242)
    assert campaign.ssh_address({"ssh_host": "proxy", "ssh_port": 1}) == ("proxy", 1)
    assert campaign.ssh_address({}) is None


def test_renting_and_launching_need_an_explicit_yes(monkeypatch):
    monkeypatch.setattr(campaign, "request", lambda *a, **k: pytest.fail("the API must not be called"))
    with pytest.raises(SystemExit, match="--yes"):
        campaign.main(["rent", "123"])
    with pytest.raises(SystemExit, match="--yes"):
        campaign.main(["launch"])
    with pytest.raises(SystemExit, match="--yes"):
        campaign.main(["stop"])


def row(**fields):
    return {"game": "g", "driver": "agent", "status": "running", "done": False, "moves": 5, "error": "", **fields}


def test_a_run_is_done_only_when_won_or_out_of_moves():
    assert campaign.finished({"status": "completed", "solved": True}, 10)
    assert campaign.finished({"status": "completed", "solved": False}, 800)
    assert not campaign.finished({"status": "completed", "solved": False, "reason": "agent_idle"}, 10)
    assert not campaign.finished({"status": "error", "solved": False}, 800)
    assert not campaign.finished({}, 800)


def test_only_a_long_silence_counts_as_hung():
    assert campaign.verdict(row(), 19) == "running" and campaign.verdict(row(), 20) == "hung"
    assert campaign.verdict(row(status="failed"), 1) == "stopped"
    assert campaign.verdict(row(status="completed", done=True), 999) == "done"


def test_the_rental_ends_only_when_no_run_can_go_on():
    done = row(verdict="done")
    assert campaign.campaign_over([done], {})
    assert not campaign.campaign_over([], {})
    assert not campaign.campaign_over([done, row(verdict="running")], {})
    assert not campaign.campaign_over([done, row(verdict="stopped")], {("g", "agent"): 19})
    assert campaign.campaign_over([done, row(verdict="stopped")], {("g", "agent"): 20})


def test_nothing_is_resumed_while_a_service_is_down_or_past_the_limit(monkeypatch):
    pending = row(verdict="stopped")
    monkeypatch.setattr(campaign, "latest_rows", lambda state: ([pending], {("g", "agent"): 0}))
    monkeypatch.setattr(campaign, "resume_run", lambda *a: pytest.fail("must not resume"))
    monkeypatch.setattr(campaign, "healthy", lambda: "the model server does not answer")
    logged = []
    campaign.tend({}, logged.append)
    assert "Not resuming" in logged[0]
    monkeypatch.setattr(campaign, "healthy", lambda: "")
    monkeypatch.setattr(campaign, "load_state", lambda: {})
    monkeypatch.setattr(campaign, "latest_rows", lambda state: ([pending], {("g", "agent"): 20}))
    campaign.tend({}, logged.append)
    assert "resumed 20 times" in logged[1]


def test_destroying_needs_a_yes(monkeypatch):
    monkeypatch.setattr(campaign, "request", lambda *a, **k: pytest.fail("the API must not be called"))
    with pytest.raises(SystemExit, match="--yes"):
        campaign.main(["destroy"])
