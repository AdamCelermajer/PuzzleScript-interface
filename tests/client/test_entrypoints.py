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

    def test_run_arc_agent_defaults_to_public_sokoban_id(self) -> None:
        from client import run_arc_agent

        captured: dict[str, object] = {}
        loop_calls: list[str] = []

        class FakeDashboard:
            def __init__(self, **kwargs) -> None:
                self.render = lambda *args, **kwargs: None
                self.push_event = lambda *args, **kwargs: None

            def close(self) -> None:
                return None

        class FakeArcadeEnv:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

        class FakeArchitecture:
            perceiver = object()
            memory = object()
            rulebook = object()
            planner = object()
            inducer = object()

            @classmethod
            def from_config(cls, cfg, llm_client, event_sink=None):
                captured["architecture_game"] = cfg.game
                return cls()

        class FakeLoop:
            def __init__(
                self,
                env,
                perceiver,
                memory,
                rulebook,
                planner,
                inducer,
                *,
                dashboard=None,
                event_sink=None,
            ) -> None:
                captured["loop_env"] = env
                captured["loop_dashboard"] = dashboard

            def run_learning(self, *, max_steps: int, game_id: str, mode: str) -> None:
                loop_calls.append(f"learn:{game_id}:{max_steps}:{mode}")

            def run_solving(self, *, max_steps: int) -> None:
                loop_calls.append(f"solve:{max_steps}")

        with (
            patch.object(sys, "argv", [RUN_AGENT_PATH]),
            patch.object(run_arc_agent, "TerminalDashboard", FakeDashboard),
            patch.object(run_arc_agent, "ArcadeEnv", FakeArcadeEnv),
            patch.object(run_arc_agent, "LlmClient", lambda *args, **kwargs: object()),
            patch.object(
                run_arc_agent, "EngineArchitecture", FakeArchitecture
            ),
            patch.object(run_arc_agent, "RuleReasoningLoop", FakeLoop),
        ):
            run_arc_agent.main()

        self.assertEqual(captured["game_id"], "ps_sokoban_basic-v1")
        self.assertEqual(captured["architecture_game"], "ps_sokoban_basic-v1")
        self.assertEqual(loop_calls, ["learn:ps_sokoban_basic-v1:50:learn"])

    def test_play_arc_client_defaults_to_public_sokoban_id(self) -> None:
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
        self.assertEqual(FakeArcade.make_calls[-1][0], "ps_sokoban_basic-v1")


if __name__ == "__main__":
    unittest.main()
