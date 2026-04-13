import os
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from arcengine import GameState


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
RUN_AGENT_PATH = os.path.join(CLIENT_DIR, "run_arc_agent.py")
PLAY_CLIENT_PATH = os.path.join(CLIENT_DIR, "play_arc_client.py")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


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

    def test_run_arc_agent_defaults_to_sokoban_basic(self) -> None:
        from client import run_arc_agent

        captured: dict[str, object] = {}

        class FakeDashboard:
            def __init__(self, **kwargs) -> None:
                self.render = lambda *args, **kwargs: None
                self.push_event = lambda *args, **kwargs: None

            def close(self) -> None:
                return None

        class FakeArcadeEnv:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

        with (
            patch.object(sys, "argv", [RUN_AGENT_PATH]),
            patch.object(run_arc_agent, "TerminalDashboard", FakeDashboard),
            patch.object(run_arc_agent, "ArcadeEnv", FakeArcadeEnv),
            patch.object(run_arc_agent, "LlmClient", lambda *args, **kwargs: object()),
            patch.object(run_arc_agent, "Agent", lambda *args, **kwargs: object()),
            patch.object(
                run_arc_agent, "run_learning_loop", lambda *args, **kwargs: None
            ),
            patch.object(
                run_arc_agent, "run_solving_loop", lambda *args, **kwargs: None
            ),
        ):
            run_arc_agent.main()

        self.assertEqual(captured["game_id"], "sokoban-basic")

    def test_play_arc_client_defaults_to_sokoban_basic(self) -> None:
        from client import play_arc_client

        class FakeDashboard:
            def __init__(self, **kwargs) -> None:
                self.render = lambda *args, **kwargs: None

            def push_event(self, message: str) -> None:
                return None

            def set_status(self, message: str) -> None:
                return None

            def set_detail(self, message: str) -> None:
                return None

            def close(self) -> None:
                return None

        class FakeEnv:
            def reset(self):
                return SimpleNamespace(
                    state=GameState.NOT_FINISHED,
                    levels_completed=0,
                    win_levels=1,
                )

        class FakeArcade:
            make_calls: list[tuple[str, object]] = []

            def __init__(self, **kwargs) -> None:
                return None

            def make(self, game_id: str, renderer=None):
                self.make_calls.append((game_id, renderer))
                return FakeEnv()

        with (
            patch.object(sys, "argv", [PLAY_CLIENT_PATH]),
            patch.object(play_arc_client, "TerminalDashboard", FakeDashboard),
            patch.object(play_arc_client, "Arcade", FakeArcade),
            patch.object(play_arc_client, "read_key", lambda: "q"),
        ):
            exit_code = play_arc_client.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeArcade.make_calls[-1][0], "sokoban-basic")


if __name__ == "__main__":
    unittest.main()
