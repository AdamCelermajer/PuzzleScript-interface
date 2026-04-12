import os
import runpy
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
RUN_AGENT_PATH = os.path.join(CLIENT_DIR, "run_arc_agent.py")
PLAY_CLIENT_PATH = os.path.join(CLIENT_DIR, "play_arc_client.py")


def _run_script_style(path: str) -> dict:
    original_path = sys.path[:]
    original_argv = sys.argv[:]
    try:
        sys.path[:] = [
            CLIENT_DIR,
            *[
                entry
                for entry in original_path
                if os.path.abspath(entry or os.curdir) != ROOT
            ],
        ]
        sys.argv = [path, "--help"]
        return runpy.run_path(path, run_name="__main__")
    except SystemExit as exc:
        if exc.code not in {0, None}:
            raise
        return {}
    finally:
        sys.path[:] = original_path
        sys.argv = original_argv


class ClientEntrypointTests(unittest.TestCase):
    def test_run_arc_agent_can_be_loaded_with_script_style_sys_path(self) -> None:
        globals_after_run = _run_script_style(RUN_AGENT_PATH)

        if globals_after_run:
            self.assertIn("main", globals_after_run)

    def test_play_arc_client_can_be_loaded_with_script_style_sys_path(self) -> None:
        globals_after_run = _run_script_style(PLAY_CLIENT_PATH)

        if globals_after_run:
            self.assertIn("main", globals_after_run)


if __name__ == "__main__":
    unittest.main()
