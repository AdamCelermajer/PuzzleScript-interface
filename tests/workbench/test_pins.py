from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.experiments import create_router

RUN = "output/workbench/20261020T104612-abc/run-0001/rollouts/base1"


def client(root):
    app = FastAPI()
    app.include_router(create_router(root))
    return TestClient(app)


def test_pins_keep_text_dedupe_by_key_and_take_notes(tmp_path):
    pin = {"run": RUN, "key": "|58|reasoning|t|Level 1 is cleared", "turn": 58, "kind": "reasoning",
           "title": "Reasoning", "text": "Level 1 is cleared! Winning condition: move to all cells", "at": "2026-10-20T08:25:37Z"}
    with client(tmp_path) as api:
        created = api.post("/api/workbench/pins", json=pin)
        assert created.status_code == 201
        assert api.post("/api/workbench/pins", json=pin).json()["id"] == created.json()["id"]
        pin_id = created.json()["id"]
        assert api.patch(f"/api/workbench/pins/{pin_id}", json={"note": "never saw the push"}).json()["note"] == "never saw the push"
        assert [p["text"] for p in api.get("/api/workbench/pins", params={"run": RUN}).json()["pins"]] == [pin["text"]]
        assert api.get("/api/workbench/pins", params={"run": "other"}).json()["pins"] == []
        assert api.delete(f"/api/workbench/pins/{pin_id}").status_code == 204
        assert api.get("/api/workbench/pins").json()["pins"] == []
        assert api.delete(f"/api/workbench/pins/{pin_id}").status_code == 404


def test_pins_reject_bad_input(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/api/workbench/pins", json={"run": "../../etc", "text": "x"}).status_code == 400
        assert api.post("/api/workbench/pins", json={"run": RUN, "text": ""}).status_code == 400
        assert api.post("/api/workbench/pins", json={"run": RUN, "text": "x", "turn": "3"}).status_code == 400
