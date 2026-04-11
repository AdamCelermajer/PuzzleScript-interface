import os
import sys
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from terminal_dashboard import (  # type: ignore[import-not-found]
    TerminalDashboard,
    format_color_grid,
    format_numeric_grid,
)


class TerminalDashboardTests(unittest.TestCase):
    def test_numeric_grid_uses_only_final_grid(self) -> None:
        formatted = format_numeric_grid(
            [
                [[0, 1], [2, 3]],
                [[3, 2], [1, 0]],
            ]
        )

        self.assertNotIn("[0, 1]", formatted)
        self.assertIn("[3, 2]", formatted)
        self.assertIn("[1, 0]", formatted)

    def test_color_grid_renders_ansi_blocks_for_final_grid(self) -> None:
        formatted = format_color_grid(
            [
                [[0, 1], [2, 3]],
                [[8, 9], [14, 15]],
            ]
        )

        self.assertIn("\x1b[38;2;249;60;49m██", formatted)
        self.assertIn("\x1b[38;2;30;147;255m██", formatted)
        self.assertNotIn("\x1b[38;2;255;255;255m██", formatted)

    def test_event_log_keeps_latest_entries(self) -> None:
        dashboard = TerminalDashboard(
            game_id="demo",
            mode="PLAY",
            interactive=False,
            output=StringIO(),
        )
        for index in range(8):
            dashboard.push_event(f"event {index}")

        self.assertEqual(dashboard.events[0], "event 2")
        self.assertEqual(dashboard.events[-1], "event 7")
        self.assertEqual(len(dashboard.events), 6)

    def test_non_interactive_push_event_still_writes_logs(self) -> None:
        output = StringIO()
        dashboard = TerminalDashboard(
            game_id="demo",
            mode="PLAY",
            interactive=False,
            output=output,
        )

        dashboard.push_event("hello world")

        self.assertIn("hello world", output.getvalue())

    def test_build_screen_truncates_to_terminal_height(self) -> None:
        dashboard = TerminalDashboard(game_id="demo", mode="PLAY", interactive=False)
        dashboard.numeric_frame_text = "\n".join(f"row {index}" for index in range(20))
        dashboard.color_frame_text = "\n".join(f"color {index}" for index in range(20))
        dashboard.events = [f"event {index}" for index in range(6)]

        with patch(
            "terminal_dashboard.shutil.get_terminal_size",
            return_value=os.terminal_size((60, 10)),
        ):
            screen = dashboard._build_screen()

        self.assertLessEqual(len(screen.splitlines()), 10)
        self.assertIn("output truncated", screen)

    def test_render_builds_side_by_side_numeric_and_color_views(self) -> None:
        dashboard = TerminalDashboard(game_id="demo", mode="PLAY", interactive=False)

        frame_data = SimpleNamespace(
            frame=[[[0, 1], [2, 3]], [[8, 9], [14, 15]]],
            state=SimpleNamespace(name="PLAYING"),
            levels_completed=0,
            win_levels=1,
            action_input=SimpleNamespace(id=SimpleNamespace(name="ACTION4")),
        )
        dashboard.render(2, frame_data)

        screen = dashboard._build_screen()

        self.assertIn("LLM View", screen)
        self.assertIn("Color View", screen)
        self.assertIn("[8, 9]", screen)
        self.assertIn("\x1b[38;2;249;60;49m██", screen)


if __name__ == "__main__":
    unittest.main()
