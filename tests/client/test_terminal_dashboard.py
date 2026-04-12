import os
import sys
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from client.terminal_dashboard import (  # type: ignore[import-not-found]
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
            "client.terminal_dashboard.shutil.get_terminal_size",
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

    def test_arc_profile_uses_compact_numeric_view_for_wide_boards(self) -> None:
        dashboard = TerminalDashboard(
            game_id="ls20",
            mode="LEARN",
            interactive=False,
            display_profile="arc",
        )

        wide_row = [5] * 34 + [4] * 26 + [3] * 4
        expected_row = "".join(str(value) for value in wide_row)
        frame_data = SimpleNamespace(
            frame=[[wide_row, wide_row]],
            state=SimpleNamespace(name="PLAYING"),
            levels_completed=0,
            win_levels=1,
            action_input=SimpleNamespace(id=SimpleNamespace(name="ACTION4")),
        )

        with patch(
            "client.terminal_dashboard.shutil.get_terminal_size",
            return_value=os.terminal_size((100, 20)),
        ):
            dashboard.render(2, frame_data)
            screen = dashboard._build_screen()

        self.assertIn("Compact View", screen)
        self.assertNotIn("Color View", screen)
        self.assertIn(expected_row, screen)
        self.assertNotIn("[5, 5, 5", screen)

    def test_arc_profile_keeps_color_view_for_small_boards(self) -> None:
        dashboard = TerminalDashboard(
            game_id="demo",
            mode="LEARN",
            interactive=False,
            display_profile="arc",
        )

        frame_data = SimpleNamespace(
            frame=[[[0, 1], [2, 3]], [[8, 9], [14, 15]]],
            state=SimpleNamespace(name="PLAYING"),
            levels_completed=0,
            win_levels=1,
            action_input=SimpleNamespace(id=SimpleNamespace(name="ACTION4")),
        )

        with patch(
            "client.terminal_dashboard.shutil.get_terminal_size",
            return_value=os.terminal_size((100, 20)),
        ):
            dashboard.render(2, frame_data)
            screen = dashboard._build_screen()

        self.assertIn("Color View", screen)
        self.assertIn("[8, 9]", screen)
        self.assertIn("\x1b[38;2;249;60;49m██", screen)

    def test_arc_profile_uses_compact_and_color_when_both_fit(self) -> None:
        dashboard = TerminalDashboard(
            game_id="ls20",
            mode="LEARN",
            interactive=False,
            display_profile="arc",
        )

        wide_row = [5] * 34 + [4] * 26 + [3] * 4
        expected_row = "".join(str(value) for value in wide_row)
        frame_data = SimpleNamespace(
            frame=[[wide_row, wide_row]],
            state=SimpleNamespace(name="PLAYING"),
            levels_completed=0,
            win_levels=1,
            action_input=SimpleNamespace(id=SimpleNamespace(name="ACTION4")),
        )

        with patch(
            "client.terminal_dashboard.shutil.get_terminal_size",
            return_value=os.terminal_size((200, 20)),
        ):
            dashboard.render(2, frame_data)
            screen = dashboard._build_screen()

        self.assertIn("Compact View", screen)
        self.assertIn("Color View", screen)
        self.assertIn(expected_row, screen)
        self.assertIn("\x1b[38;2;", screen)
        self.assertIn("██", screen)
        self.assertNotIn("[5, 5, 5", screen)


if __name__ == "__main__":
    unittest.main()
