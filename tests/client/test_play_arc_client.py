import os
import sys
import unittest

from arcengine import GameAction


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from client.play_arc_client import (  # type: ignore[import-not-found]
    QUIT_COMMAND,
    key_to_action,
)


class PlayArcClientTests(unittest.TestCase):
    def test_key_to_action_maps_expected_controls(self) -> None:
        self.assertEqual(key_to_action("w"), GameAction.ACTION1)
        self.assertEqual(key_to_action("a"), GameAction.ACTION3)
        self.assertEqual(key_to_action("s"), GameAction.ACTION2)
        self.assertEqual(key_to_action("d"), GameAction.ACTION4)
        self.assertEqual(key_to_action("r"), GameAction.RESET)
        self.assertEqual(key_to_action("z"), GameAction.ACTION7)
        self.assertEqual(key_to_action("q"), QUIT_COMMAND)

    def test_key_to_action_is_case_insensitive_and_ignores_unknown_keys(self) -> None:
        self.assertEqual(key_to_action("W"), GameAction.ACTION1)
        self.assertIsNone(key_to_action("x"))
        self.assertIsNone(key_to_action(""))


if __name__ == "__main__":
    unittest.main()
