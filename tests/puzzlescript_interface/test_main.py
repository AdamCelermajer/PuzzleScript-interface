import os
import runpy
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN_PATH = os.path.join(ROOT, "puzzlescript_interface", "api", "main.py")
API_DIR = os.path.dirname(MAIN_PATH)


class MainEntrypointTests(unittest.TestCase):
    def test_main_can_be_loaded_with_script_style_sys_path(self) -> None:
        original_path = sys.path[:]
        try:
            sys.path[:] = [
                API_DIR,
                *[
                    entry
                    for entry in original_path
                    if os.path.abspath(entry or os.curdir) != ROOT
                ],
            ]

            globals_after_run = runpy.run_path(MAIN_PATH)

            self.assertIn("app", globals_after_run)
        finally:
            sys.path[:] = original_path


if __name__ == "__main__":
    unittest.main()
