from __future__ import annotations

import atexit
import os
import shutil
import sys
import textwrap
import threading
from dataclasses import dataclass, field
from typing import Any

from arc_agi.rendering import COLOR_MAP, hex_to_rgb, rgb_to_ansi

from client.engine.utils import format_grid, last_grid


CSI = "\x1b["
ENTER_ALT_SCREEN = f"{CSI}?1049h"
EXIT_ALT_SCREEN = f"{CSI}?1049l"
HIDE_CURSOR = f"{CSI}?25l"
SHOW_CURSOR = f"{CSI}?25h"
HOME = f"{CSI}H"
CLEAR_SCREEN = f"{CSI}2J"


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _normalize_grid(grid: Any) -> list[list[int]]:
    if hasattr(grid, "tolist"):
        grid = grid.tolist()
    return [[int(value) for value in row] for row in grid]


def _format_numeric_grid(grid: list[list[int]]) -> str:
    if not grid:
        return "(no frame yet)"
    return format_grid(grid)


def _format_color_grid(grid: list[list[int]]) -> str:
    if not grid:
        return "(no frame yet)"

    reset = "\033[0m"
    block = "██"
    lines = []
    for row in grid:
        color_line = []
        for value in row:
            rgb = hex_to_rgb(COLOR_MAP.get(int(value), "#000000FF"))
            color_line.append(f"{rgb_to_ansi(rgb)}{block}{reset}")
        lines.append("".join(color_line))
    return "\n".join(lines)


def _compact_symbol(value: int) -> str:
    digits = "0123456789ABCDEF"
    if 0 <= value < len(digits):
        return digits[value]
    return "?"


def _format_compact_grid(grid: list[list[int]]) -> str:
    if not grid:
        return "(no frame yet)"
    return "\n".join(
        "".join(_compact_symbol(int(value)) for value in row) for row in grid
    )


def format_numeric_grid(frames: list[Any]) -> str:
    grid = last_grid(frames)
    return _format_numeric_grid(grid)


def format_color_grid(frames: list[Any]) -> str:
    grid = last_grid(frames)
    return _format_color_grid(grid)


def _merge_columns(left: list[str], right: list[str], gap: str = "    ") -> list[str]:
    left_width = max((len(line) for line in left), default=0)
    total_lines = max(len(left), len(right))
    merged = []
    for index in range(total_lines):
        left_line = left[index] if index < len(left) else ""
        right_line = right[index] if index < len(right) else ""
        merged.append(left_line.ljust(left_width) + gap + right_line)
    return merged


@dataclass
class TerminalDashboard:
    game_id: str
    mode: str
    controls: str = ""
    max_events: int = 6
    display_profile: str = "puzzlescript"
    output: Any = sys.stdout
    interactive: bool | None = None
    step: int = 0
    state: str = "NOT_STARTED"
    levels_completed: int = 0
    win_levels: int = 0
    last_action: str = ""
    status: str = ""
    detail: str = ""
    numeric_frame_text: str = "(no frame yet)"
    color_frame_text: str = "(no frame yet)"
    compact_frame_text: str = "(no frame yet)"
    board_rows: int = 0
    board_cols: int = 0
    events: list[str] = field(default_factory=list)
    _active: bool = field(default=False, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        _enable_windows_ansi()
        self.display_profile = (
            str(self.display_profile or "puzzlescript").strip().lower()
        )
        if self.interactive is None:
            self.interactive = bool(getattr(self.output, "isatty", lambda: False)())
        atexit.register(self.close)

    def render(self, steps: int, frame_data: Any) -> None:
        with self._lock:
            self.step = int(steps)
            frames = getattr(frame_data, "frame", []) or []
            grid = last_grid(frames)
            self.numeric_frame_text = _format_numeric_grid(grid)
            self.color_frame_text = _format_color_grid(grid)
            self.compact_frame_text = _format_compact_grid(grid)
            self.board_rows = len(grid)
            self.board_cols = max((len(row) for row in grid), default=0)
            state = getattr(frame_data, "state", "")
            self.state = getattr(state, "name", str(state or "UNKNOWN"))
            self.levels_completed = int(getattr(frame_data, "levels_completed", 0))
            self.win_levels = int(getattr(frame_data, "win_levels", 0))
            action_input = getattr(frame_data, "action_input", None)
            action_id = getattr(action_input, "id", "") if action_input else ""
            self.last_action = getattr(action_id, "name", str(action_id or ""))
            self._redraw_locked()

    def push_event(self, message: str) -> None:
        cleaned = " ".join(str(message).split())
        if not cleaned:
            return
        with self._lock:
            self.events.append(cleaned)
            self.events = self.events[-self.max_events :]
            if not self.interactive:
                self.output.write(f"{cleaned}\n")
                self.output.flush()
                return
            self._redraw_locked()

    def set_status(self, message: str) -> None:
        with self._lock:
            self.status = str(message).strip()
            self._redraw_locked()

    def set_detail(self, message: str) -> None:
        with self._lock:
            self.detail = str(message).strip()
            self._redraw_locked()

    def close(self) -> None:
        with self._lock:
            if not self._active or not self.interactive:
                return
            self.output.write(f"{SHOW_CURSOR}{EXIT_ALT_SCREEN}")
            self.output.flush()
            self._active = False

    def _redraw_locked(self) -> None:
        if not self.interactive:
            return
        if not self._active:
            self.output.write(f"{ENTER_ALT_SCREEN}{HIDE_CURSOR}")
            self._active = True
        self.output.write(f"{HOME}{CLEAR_SCREEN}{self._build_screen()}")
        self.output.flush()

    def _build_screen(self) -> str:
        terminal_size = shutil.get_terminal_size((100, 40))
        width = terminal_size.columns
        height = terminal_size.lines
        divider = "=" * max(40, min(width, 100))
        section = "-" * max(20, min(width, 80))
        lines = [
            divider,
            self._title(),
            f"Game: {self.game_id} | Mode: {self.mode} | Turn: {self.step}",
            f"State: {self.state} | Levels: {self.levels_completed}/{self.win_levels}",
        ]
        if self.last_action:
            lines.append(f"Last action: {self.last_action}")
        lines.extend(self._wrap_line("Status", self.status, width))
        lines.extend(self._wrap_line("Detail", self.detail, width))
        lines.extend(
            [
                section,
                *self._build_board_lines(width),
                section,
                "Recent events:",
            ]
        )
        if self.events:
            lines.extend(f"- {event}" for event in self.events)
        else:
            lines.append("(none yet)")
        if self.controls:
            lines.extend([section, f"Controls: {self.controls}"])
        lines.append(divider)
        max_lines = max(8, height)
        screen_lines = "\n".join(lines).splitlines()
        if len(screen_lines) > max_lines:
            screen_lines = screen_lines[: max_lines - 2] + [
                "... output truncated to fit terminal ...",
                divider,
            ]
        return "\n".join(screen_lines)

    def _title(self) -> str:
        if self.display_profile == "arc":
            return "ARC Terminal"
        return "PuzzleScript Terminal"

    def _build_board_lines(self, width: int) -> list[str]:
        numeric_lines = self.numeric_frame_text.splitlines()
        color_lines = self.color_frame_text.splitlines()
        compact_lines = self.compact_frame_text.splitlines()

        if self._can_fit_side_by_side(width):
            return [
                "Board:",
                *_merge_columns(
                    ["LLM View", *numeric_lines],
                    ["Color View", *color_lines],
                ),
            ]

        if self._can_fit_compact_and_color(width):
            return [
                "Board:",
                *_merge_columns(
                    ["Compact View", *compact_lines],
                    ["Color View", *color_lines],
                ),
            ]

        if self._should_use_compact_view(width):
            return ["Board:", "Compact View", *compact_lines]

        return [
            "Board:",
            "LLM View",
            *numeric_lines,
            "Color View",
            *color_lines,
        ]

    def _should_use_compact_view(self, width: int) -> bool:
        numeric_width = self._frame_width(self.numeric_frame_text)
        color_width = self._color_view_width()
        if self.display_profile == "arc" and self._is_large_arc_board():
            return True
        return max(numeric_width, color_width) > width

    def _can_fit_side_by_side(self, width: int) -> bool:
        numeric_width = max(self._frame_width(self.numeric_frame_text), len("LLM View"))
        color_width = max(self._color_view_width(), len("Color View"))
        return numeric_width + 4 + color_width <= width

    def _can_fit_compact_and_color(self, width: int) -> bool:
        compact_width = max(
            self._frame_width(self.compact_frame_text), len("Compact View")
        )
        color_width = max(self._color_view_width(), len("Color View"))
        return compact_width + 4 + color_width <= width

    def _frame_width(self, text: str) -> int:
        return max((len(line) for line in text.splitlines()), default=0)

    def _color_view_width(self) -> int:
        if self.board_cols:
            return self.board_cols * 2
        return self._frame_width(self.color_frame_text)

    def _is_large_arc_board(self) -> bool:
        if not self.board_rows or not self.board_cols:
            return False
        return (
            self.board_cols >= 30
            or self.board_rows >= 20
            or self.board_rows * self.board_cols >= 400
        )

    def _wrap_line(self, label: str, text: str, width: int) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        wrapped = textwrap.wrap(
            cleaned,
            width=max(20, width - len(label) - 2),
            break_long_words=False,
            break_on_hyphens=False,
        )
        if not wrapped:
            return []
        return [
            f"{label}: {wrapped[0]}",
            *[f"{' ' * (len(label) + 2)}{line}" for line in wrapped[1:]],
        ]
