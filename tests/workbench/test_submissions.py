import io
import json
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.experiments import ExperimentRequest, create_router, plan_runs
from workbench.submissions import submission, submission_file


def test_best_submission_uses_evaluated_solver_and_preserves_helpers():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        run = "output/batch/campaign"
        path = root / run
        path.mkdir(parents=True)
        (path / "evolution_config.json").write_text('{}')
        (path / "lineage.json").write_text(json.dumps({"evaluations": [
            {"candidate_id": "x_0001", "fitness": 2}, {"candidate_id": "x_0002", "fitness": 2},
            {"candidate_id": "x_0003", "fitness": 0}]}))
        for candidate in ("x_0001", "x_0002", "x_0003"):
            solver = path / candidate / "solver"
            solver.mkdir(parents=True)
            (solver / "solver.py").write_text(candidate)
        (path / "x_0001/solver/helper.json").write_text('{"state":1}')
        (path / "x_0001/solver/world_model.md").write_text('inner input')
        (path / "world_model.md").write_text('final outer report')
        result = submission(run, root)
        assert result["best"]["candidate_id"] == "x_0001"
        assert result["solver_present"]
        app = FastAPI()
        app.include_router(create_router(root))
        client = TestClient(app)
        response = client.get('/api/workbench/submission/download', params={"run": run})
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read('solver/solver.py') == b'x_0001'
            assert archive.read('solver/helper.json') == b'{"state":1}'
            assert archive.read('solver/world_model.md') == b'inner input'
            assert archive.read('world_model.md') == b'final outer report'
        assert client.get('/api/workbench/submission/file', params={"run":run,"file":"../private"}).status_code == 400
        assert client.get('/api/workbench/submission/file', params={"run":run,"file":"x_0002/solver/solver.py"}).text == 'x_0002'
        assert client.get('/api/workbench/submission/file', params={"run":run,"file":"x_0004/solver/solver.py"}).status_code == 400


def test_legacy_layout_and_missing_solver_remain_truthful():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        run = "avo/output/old"
        path = root / run
        path.mkdir(parents=True)
        (path / "evolution_config.json").write_text('{}')
        (path / "population.json").write_text(json.dumps({"evaluations":[{"candidate_id":"x_0001","evaluation_id":"run_001","fitness":0}]}))
        assert not submission(run, root)["solver_present"]
        target = path / "evaluations/x_0001/run_001/workspace/solver.py"
        target.parent.mkdir(parents=True)
        target.write_text('evaluated')
        assert submission_file(run, 'evaluations/x_0001/run_001/workspace/solver.py', root) == target
        assert submission(run, root)["world_model"] is None


def test_world_model_comparison_creates_separate_campaigns():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        config = ExperimentRequest(kind="avo", game_ids=["a", "b"], repeats=2,
                                   world_model_modes=["final-only", "between-hypotheses"])
        rows = plan_runs(config, root / "output/batch", root)
        assert len(rows) == 8
        assert len({r['output'] for r in rows}) == 8
        assert {r['world_model_mode'] for r in rows} == {'final-only','between-hypotheses'}
        for row in rows:
            cmd = row['command']
            assert cmd[cmd.index('--world-model-mode') + 1] == row['world_model_mode']
        assert not (root / 'output').exists()
