import os
import sys
import unittest

from arcengine import FrameData
from fastapi import HTTPException
from fastapi.testclient import TestClient


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from puzzlescript_interface.api.app import create_app  # type: ignore[import-not-found]
from puzzlescript_interface.api.catalog import (  # type: ignore[import-not-found]
    GameCatalogEntry,
)


class FakePuzzleScriptClient:
    def __init__(self) -> None:
        self.started_games: list[str] = []
        self.actions: list[tuple[str, str]] = []
        self.fail_next_start: tuple[int, str] | None = None

    def start_game(self, source_name: str) -> dict:
        if self.fail_next_start is not None:
            status_code, detail = self.fail_next_start
            self.fail_next_start = None
            raise HTTPException(status_code=status_code, detail=detail)
        self.started_games.append(source_name)
        return {
            "sessionId": "ps-session-1",
            "frame": [[[0, 1], [1, 0]]],
            "state": "PLAYING",
            "levels_completed": 0,
            "win_levels": 2,
            "available_actions": [
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
                "ACTION5",
                "ACTION7",
            ],
        }

    def reset_session(self, session_id: str) -> dict:
        return {
            "frame": [[[0, 1], [1, 0]]],
            "state": "PLAYING",
            "levels_completed": 0,
            "win_levels": 2,
            "available_actions": [
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
                "ACTION5",
                "ACTION7",
            ],
        }

    def apply_action(self, session_id: str, action_name: str) -> dict:
        self.actions.append((session_id, action_name))
        return {
            "frame": [[[1, 0], [0, 1]]],
            "state": "PLAYING",
            "levels_completed": 1,
            "win_levels": 2,
            "available_actions": [
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
                "ACTION5",
                "ACTION7",
            ],
        }

    def observe(self, session_id: str) -> dict:
        return {
            "frame": [[[1, 0], [0, 1]]],
            "state": "PLAYING",
            "levels_completed": 1,
            "win_levels": 2,
            "available_actions": [
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
                "ACTION5",
                "ACTION7",
            ],
        }


class ArcServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = [
            GameCatalogEntry(
                game_id="sokoban-basic",
                title="sokoban-basic",
                source_name="sokoban-basic",
                file_path=os.path.join(
                    ROOT,
                    "puzzlescript_interface",
                    "games",
                    "sokoban-basic",
                    "script.txt",
                ),
            ),
            GameCatalogEntry(
                game_id="midas",
                title="midas",
                source_name="midas",
                file_path=os.path.join(
                    ROOT, "puzzlescript_interface", "games", "midas", "script.txt"
                ),
            ),
        ]
        self.fake_client = FakePuzzleScriptClient()
        self.client = TestClient(
            create_app(catalog=self.catalog, puzzlescript_client=self.fake_client)
        )

    def test_games_endpoint_returns_folder_name_game_ids(self) -> None:
        response = self.client.get("/api/games")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"game_id": "sokoban-basic", "title": "sokoban-basic"},
                {"game_id": "midas", "title": "midas"},
            ],
        )

    def test_default_games_endpoint_uses_folder_name_ids(self) -> None:
        client = TestClient(create_app())

        response = client.get("/api/games")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            {"game_id": "sokoban-basic", "title": "sokoban-basic"},
            response.json(),
        )
        self.assertNotIn(
            {"game_id": "sokoban-basic-v1", "title": "sokoban-basic"},
            response.json(),
        )

    def test_game_info_endpoint_accepts_folder_name_lookup(self) -> None:
        response = self.client.get("/api/games/sokoban-basic")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["game_id"], "sokoban-basic")
        self.assertEqual(response.json()["title"], "sokoban-basic")

    def test_scorecard_lifecycle_tracks_reset_and_actions(self) -> None:
        open_response = self.client.post(
            "/api/scorecard/open", json={"tags": ["local"]}
        )
        self.assertEqual(open_response.status_code, 200)
        card_id = open_response.json()["card_id"]

        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )
        self.assertEqual(reset_response.status_code, 200)
        reset_body = reset_response.json()
        FrameData.model_validate(reset_body)
        self.assertEqual(self.fake_client.started_games, ["sokoban-basic"])
        self.assertEqual(reset_body["available_actions"], [1, 2, 3, 4, 5, 7])

        guid = reset_body["guid"]
        action_response = self.client.post(
            "/api/cmd/ACTION1",
            json={
                "game_id": "sokoban-basic",
                "guid": guid,
                "reasoning": {"policy": "test"},
            },
        )
        self.assertEqual(action_response.status_code, 200)
        action_body = action_response.json()
        FrameData.model_validate(action_body)
        self.assertEqual(self.fake_client.actions, [("ps-session-1", "ACTION1")])

        scorecard_response = self.client.get(f"/api/scorecard/{card_id}")
        self.assertEqual(scorecard_response.status_code, 200)
        scorecard_body = scorecard_response.json()
        self.assertEqual(scorecard_body["total_actions"], 1)
        self.assertEqual(scorecard_body["total_environments"], 1)
        self.assertEqual(scorecard_body["total_levels"], 2)
        self.assertEqual(scorecard_body["tags"], ["local"])

        close_response = self.client.post(
            "/api/scorecard/close", json={"card_id": card_id}
        )
        self.assertEqual(close_response.status_code, 200)
        self.assertIn("published_at", close_response.json())

    def test_action6_is_rejected(self) -> None:
        open_response = self.client.post("/api/scorecard/open", json={})
        card_id = open_response.json()["card_id"]
        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )
        guid = reset_response.json()["guid"]

        response = self.client.post(
            "/api/cmd/ACTION6",
            json={"game_id": "sokoban-basic", "guid": guid},
        )

        self.assertEqual(response.status_code, 400)

    def test_action7_is_forwarded_to_the_backend(self) -> None:
        open_response = self.client.post("/api/scorecard/open", json={})
        card_id = open_response.json()["card_id"]
        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )
        guid = reset_response.json()["guid"]

        response = self.client.post(
            "/api/cmd/ACTION7",
            json={"game_id": "sokoban-basic", "guid": guid},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_client.actions[-1], ("ps-session-1", "ACTION7"))

    def test_closed_scorecards_reject_new_resets(self) -> None:
        open_response = self.client.post("/api/scorecard/open", json={})
        card_id = open_response.json()["card_id"]

        close_response = self.client.post(
            "/api/scorecard/close", json={"card_id": card_id}
        )
        self.assertEqual(close_response.status_code, 200)

        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )

        self.assertEqual(reset_response.status_code, 404)

    def test_guid_reset_requires_matching_card_id(self) -> None:
        first_card = self.client.post("/api/scorecard/open", json={}).json()["card_id"]
        second_card = self.client.post("/api/scorecard/open", json={}).json()["card_id"]
        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": first_card, "game_id": "sokoban-basic"},
        )
        guid = reset_response.json()["guid"]

        mismatched_reset = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": second_card, "game_id": "sokoban-basic", "guid": guid},
        )

        self.assertEqual(mismatched_reset.status_code, 400)

    def test_guid_reset_requires_matching_game_id(self) -> None:
        card_id = self.client.post("/api/scorecard/open", json={}).json()["card_id"]
        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )
        guid = reset_response.json()["guid"]

        mismatched_reset = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "midas", "guid": guid},
        )

        self.assertEqual(mismatched_reset.status_code, 400)

    def test_actions_after_scorecard_close_are_rejected_cleanly(self) -> None:
        card_id = self.client.post("/api/scorecard/open", json={}).json()["card_id"]
        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )
        guid = reset_response.json()["guid"]
        close_response = self.client.post(
            "/api/scorecard/close", json={"card_id": card_id}
        )
        self.assertEqual(close_response.status_code, 200)

        action_response = self.client.post(
            "/api/cmd/ACTION1",
            json={"game_id": "sokoban-basic", "guid": guid},
        )

        self.assertEqual(action_response.status_code, 404)

    def test_backend_http_failures_are_preserved_in_arc_service_responses(self) -> None:
        self.fake_client.fail_next_start = (404, 'Game "missing" not found.')
        card_id = self.client.post("/api/scorecard/open", json={}).json()["card_id"]

        response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn('Game "missing" not found.', response.json()["detail"])

    def test_game_over_runs_do_not_count_as_completed(self) -> None:
        card_id = self.client.post("/api/scorecard/open", json={}).json()["card_id"]
        reset_response = self.client.post(
            "/api/cmd/RESET",
            json={"card_id": card_id, "game_id": "sokoban-basic"},
        )
        guid = reset_response.json()["guid"]
        self.fake_client.apply_action = lambda session_id, action_name: {
            "frame": [[[1, 0], [0, 1]]],
            "state": "GAME_OVER",
            "levels_completed": 0,
            "win_levels": 2,
            "available_actions": ["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
        }

        action_response = self.client.post(
            "/api/cmd/ACTION1",
            json={"game_id": "sokoban-basic", "guid": guid},
        )
        self.assertEqual(action_response.status_code, 200)

        scorecard_response = self.client.get(f"/api/scorecard/{card_id}")
        scorecard_body = scorecard_response.json()
        self.assertEqual(scorecard_body["total_environments_completed"], 0)
        self.assertEqual(scorecard_body["total_levels_completed"], 0)


if __name__ == "__main__":
    unittest.main()
