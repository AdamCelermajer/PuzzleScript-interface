import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.comparisons import comparison
from workbench.experiments import ExperimentRequest, create_router, plan_runs
from workbench.experiment_job import next_rows
from workbench.model_catalog import normalize, catalog, _cache


def test_comparison_pairs_share_settings_and_schedule_together(tmp_path):
    request = ExperimentRequest(kind="avo", game_ids=["one","two"], models=["sol","luna"], efforts=["low"],
        comparison=True, parallel=2, repeats=2, max_evaluations=10, research_moves=300)
    rows = plan_runs(request, tmp_path/"output/workbench/job", tmp_path)
    assert len(rows) == 16
    for index in range(0,len(rows),2):
        a,b=rows[index:index+2]
        assert a["pair_id"] == b["pair_id"]
        assert a["world_model_mode"] == "final-only"
        assert b["world_model_mode"] == "between-hypotheses"
        for key in ["game_id","model","effort","optimizer_model","repeat"]:
            assert a[key] == b[key]
        for flag in ["--max-evaluations","--research-moves","--solver-moves","--max-wall-seconds"]:
            assert a["command"][a["command"].index(flag)+1] == b["command"][b["command"].index(flag)+1]
    assert next_rows(rows, 2, True) == rows[:2]
    assert next_rows(rows, 1, True) == []
    rows[0]["status"]="completed"; rows[1]["status"]="running"
    assert next_rows(rows, 1, True) == []
    assert next_rows(rows, 2, True) == rows[2:4]
    for settings in [{"kind":"codex","parallel":2},{"kind":"avo","parallel":1},{"kind":"avo","parallel":3}]:
        with pytest.raises(ValueError): ExperimentRequest(game_ids=["one"],comparison=True,**settings)


def fixture(tmp_path):
    job="output/workbench/comparison-test"
    directory=tmp_path/job;directory.mkdir(parents=True)
    config=ExperimentRequest(kind="avo",game_ids=["one"],comparison=True,parallel=2)
    rows=plan_runs(config,directory,tmp_path)
    (directory/"job.json").write_text(json.dumps({"config":config.model_dump(),"runs":rows}))
    for row in rows:
        path=tmp_path/row["id"];path.mkdir(parents=True)
        (path/"evolution_config.json").write_text('{}')
    return job,rows


def test_comparison_preserves_zero_missing_and_first_success(tmp_path):
    job,rows=fixture(tmp_path)
    a=tmp_path/rows[0]["id"];b=tmp_path/rows[1]["id"]
    (a/"lineage.json").write_text(json.dumps({"evaluations":[{"candidate_id":"x_0001","fitness":0,"score":{}}]}))
    live={"runs":[{"id":rows[0]["id"],"status":"failed"},{"id":rows[1]["id"],"status":"running"}]}
    data=comparison(job,tmp_path,live)
    runs=data["pairs"][0]["runs"]
    assert runs["final-only"]["best_fitness"] == 0
    assert runs["between-hypotheses"]["best_fitness"] is None
    assert runs["final-only"]["research_actions"] is None
    assert runs["final-only"]["status"] == "failed"
    assert not runs["between-hypotheses"]["finalized"]
    (b/"lineage.json").write_text(json.dumps({"evaluations":[
        {"candidate_id":"x_0001","fitness":1,"environment_steps":30,"score":{"research_environment_actions":20,"search_session_elapsed_seconds":10}},
        {"candidate_id":"x_0002","fitness":4,"success":True,"environment_steps":40,"score":{"research_environment_actions":25,"search_session_elapsed_seconds":50}}]}))
    result=comparison(job,tmp_path,live)["pairs"][0]["runs"]["between-hypotheses"]
    assert result["solved"] and result["first_success_evaluation"] == 2
    assert result["seconds_to_success"] == 50
    assert result["research_actions"] == 45 and result["solver_actions"] == 40
    assert result["best_candidate"] == "x_0002"
    assert len(result["history"]) == 2
    with pytest.raises(ValueError): comparison("output/other",tmp_path,live)
    with pytest.raises(ValueError): comparison("../private",tmp_path,live)


def test_public_catalog_filters_tools_without_fabricated_prices():
    router=normalize("openrouter",{"data":[
        {"id":"plain/text","supported_parameters":[]},
        {"id":"a/model:batch","supported_parameters":["tools"]},
        {"id":"~alias/model","supported_parameters":["tools"]},
        {"id":"a/free:free","supported_parameters":["tools"],"pricing":{"prompt":"0","completion":"0"}},
        {"id":"b/paid","supported_parameters":["tools"],"pricing":{"prompt":"0.000002","completion":"0.000006"}},
        {"id":"c/unknown","supported_parameters":["tools"]}]})
    assert len(router)==3
    assert router[0]["free"]
    assert router[1]["input_price"]==2 and router[1]["output_price"]==6
    assert router[2]["input_price"] is None and not router[2]["free"]


def test_catalog_failure_is_explicit_and_does_not_replace_cached_values():
    import requests
    _cache.clear()
    with patch("workbench.model_catalog.requests.get",side_effect=requests.ConnectionError):
        with pytest.raises(ValueError): catalog("openrouter")
        _cache["openrouter"]={"models":[{"id":"recorded"}],"fetched_at":0}
        result=catalog("openrouter")
        assert result["stale"] and result["models"] == [{"id":"recorded"}]
    _cache.clear()


def test_comparison_preview_is_read_only_and_returns_pairs(tmp_path):
    app=FastAPI();app.include_router(create_router(tmp_path))
    with TestClient(app) as client, patch("workbench.experiments.subprocess.Popen") as popen:
        response=client.post("/api/workbench/experiments/preview",json={"kind":"avo","game_ids":["a"],"comparison":True,"parallel":2})
        assert response.status_code == 200
        data=response.json();assert data["count"]==2 and data["comparison"]
        assert data["campaigns"][0]["pair_id"]==data["campaigns"][1]["pair_id"]
        popen.assert_not_called()
        assert not (tmp_path/"output").exists()
        assert client.get("/api/workbench/comparison",params={"job":"output/workbench/missing"}).status_code==400
        launched=client.post("/api/workbench/experiments",json={"kind":"avo","game_ids":["a"],"comparison":True,"parallel":2})
        assert launched.status_code==202
        job_id=launched.json()["id"]
        manifest=json.loads((tmp_path/job_id/"job.json").read_text())
        assert manifest["config"]["comparison"]
        assert len(manifest["runs"])==2
        assert len({row["pair_id"] for row in manifest["runs"]})==1
        assert len({row["output"] for row in manifest["runs"]})==2
        popen.assert_called_once()
        with patch("workbench.catalog.live_containers",return_value=({},None)):
            record=client.get("/api/workbench/comparison",params={"job":job_id})
        assert record.status_code==200
        assert len(record.json()["pairs"])==1
        assert all(r["status"]=="queued" and r["best_fitness"] is None for r in record.json()["pairs"][0]["runs"].values())
