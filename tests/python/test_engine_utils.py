import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from engine.utils import format_frames, last_grid  # type: ignore[import-not-found]


class EngineUtilsTests(unittest.TestCase):
    def test_last_grid_returns_final_grid_only(self) -> None:
        frames = [
            [[0, 1], [1, 0]],
            [[2, 3], [3, 2]],
        ]

        self.assertEqual(last_grid(frames), [[2, 3], [3, 2]])

    def test_format_frames_uses_only_final_grid(self) -> None:
        formatted = format_frames(
            [
                [[0, 1], [1, 0]],
                [[2, 3], [3, 2]],
            ]
        )

        self.assertNotIn("Grid 0", formatted)
        self.assertNotIn("[0, 1]", formatted)
        self.assertIn("[2, 3]", formatted)
        self.assertIn("[3, 2]", formatted)


if __name__ == "__main__":
    unittest.main()
