import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import requests

from avo.core.framework import Action
from avo.environments.puzzlescript.adapter import PuzzleScriptEnvironment
from avo.isolation import IsolationError


class FailingEnvironment:
    def __init__(self, status):
        self.status = status

    def step(self, action, data):
        response = requests.Response()
        response.status_code = self.status
        response._content = b'{"detail":"BUG: Iterated too many times"}'
        raise requests.HTTPError("backend failed", response=response)


class BackendFailureTests(unittest.TestCase):
    def test_server_error_stops_the_campaign_with_engine_detail(self):
        environment = PuzzleScriptEnvironment(FailingEnvironment(500))
        with self.assertRaisesRegex(IsolationError, "HTTP 500 during ACTION5: BUG: Iterated too many times"):
            environment.step(Action("ACTION5"))

    def test_bad_action_is_not_misclassified_as_backend_failure(self):
        environment = PuzzleScriptEnvironment(FailingEnvironment(400))
        with self.assertRaises(requests.HTTPError):
            environment.step(Action("ACTION5"))

    def test_enqueue_only_catalog_excludes_other_games(self):
        from puzzlescript_interface.api.app import create_app
        from puzzlescript_interface.api.catalog import GameCatalogEntry
        from fastapi.testclient import TestClient

        with patch.dict("os.environ", {"PUZZLESCRIPT_ONLY_GAME_ID": "ps_enqueue-v1"}):
            app = create_app(catalog=[
                GameCatalogEntry("ps_enqueue-v1", "Enqueue", "ps_enqueue-v1", None),
                GameCatalogEntry("ps_other-v1", "Other", "ps_other-v1", None),
            ], puzzlescript_client=object())
        client = TestClient(app)
        self.assertEqual([entry["game_id"] for entry in client.get("/api/games").json()], ["ps_enqueue-v1"])
        self.assertEqual(client.get("/api/games/ps_other-v1").status_code, 404)

    def test_campaign_writes_needs_assistance_artifact(self):
        from avo.evolve import _record_infrastructure_failure

        with tempfile.TemporaryDirectory() as raw:
            _record_infrastructure_failure(Path(raw), IsolationError(
                "PuzzleScript backend failure: HTTP 500 during ACTION5"
            ))
            artifact = json.loads((Path(raw) / "error.json").read_text())
        self.assertEqual(artifact["status"], "needs_assistance")
        self.assertEqual(artifact["kind"], "puzzlescript_backend_failure")


if __name__ == "__main__":
    unittest.main()
