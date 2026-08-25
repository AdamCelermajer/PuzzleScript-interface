import unittest
from unittest.mock import patch

from puzzlescript_interface.api.client import PuzzleScriptClient


class PuzzleScriptClientTests(unittest.TestCase):
    def test_start_game_can_select_a_reference_level(self):
        client = PuzzleScriptClient("http://runtime.test")
        with patch.object(
            client,
            "_request",
            return_value={"sessionId": "session"},
        ) as request:
            client.start_game("ps_test-v1", level_index=3)

        request.assert_called_once_with(
            "POST",
            "/init",
            {"gameName": "ps_test-v1", "levelIndex": 3},
        )

    def test_start_game_omits_level_index_for_normal_arc_runs(self):
        client = PuzzleScriptClient("http://runtime.test")
        with patch.object(
            client,
            "_request",
            return_value={"sessionId": "session"},
        ) as request:
            client.start_game("ps_test-v1")

        request.assert_called_once_with(
            "POST",
            "/init",
            {"gameName": "ps_test-v1"},
        )


if __name__ == "__main__":
    unittest.main()
