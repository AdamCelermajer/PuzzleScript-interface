from __future__ import annotations

import tkinter as tk
import threading
from queue import Empty, Queue
from dataclasses import dataclass, field
from typing import Any, Callable

from client.engine.utils import last_grid


def _compact_symbol(value: int) -> str:
    digits = "0123456789ABCDEF"
    if 0 <= value < len(digits):
        return digits[value]
    return "?"


def format_arc_frame(frames: list[Any]) -> str:
    grid = last_grid(frames)
    if not grid:
        return "(no frame yet)"
    return "\n".join(
        " ".join(_compact_symbol(int(value)) for value in row) for row in grid
    )


def extract_png_base64(rendered_frame: Any) -> str | None:
    if not rendered_frame:
        return None
    if isinstance(rendered_frame, dict):
        mime_type = str(rendered_frame.get("mime_type", "") or "")
        data_url = str(rendered_frame.get("data_url", "") or "")
    else:
        mime_type = str(getattr(rendered_frame, "mime_type", "") or "")
        data_url = str(getattr(rendered_frame, "data_url", "") or "")
    prefix = "data:image/png;base64,"
    if mime_type != "image/png" or not data_url.startswith(prefix):
        return None
    return data_url[len(prefix) :]


@dataclass
class ScreenDashboard:
    game_id: str
    mode: str
    controls: str = ""
    max_events: int = 8
    ui_poll_ms: int = 33
    step: int = 0
    state: str = "NOT_STARTED"
    levels_completed: int = 0
    win_levels: int = 0
    last_action: str = ""
    status: str = ""
    detail: str = ""
    events: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._messages: Queue[tuple] = Queue()
        self._engine_thread: threading.Thread | None = None
        self._engine_error: BaseException | None = None
        self.root = tk.Tk()
        self.root.title(f"PuzzleScript engine - {self.game_id}")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._closed = False
        self._photo: tk.PhotoImage | None = None

        self.header_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.image_var = tk.StringVar(value="No PNG frame yet")

        self._build_layout()
        self._refresh_labels()

    def _build_layout(self) -> None:
        self.root.geometry("1120x720")
        self.root.minsize(780, 480)

        header = tk.Label(
            self.root,
            textvariable=self.header_var,
            anchor="w",
            font=("Consolas", 11, "bold"),
            padx=10,
            pady=6,
        )
        header.pack(fill=tk.X)

        body = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=6)
        body.pack(fill=tk.BOTH, expand=True)

        image_frame = tk.Frame(body, background="#202020")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
        self.image_canvas = tk.Canvas(
            image_frame,
            background="#202020",
            highlightthickness=0,
        )
        image_y = tk.Scrollbar(
            image_frame,
            orient=tk.VERTICAL,
            command=self.image_canvas.yview,
        )
        image_x = tk.Scrollbar(
            image_frame,
            orient=tk.HORIZONTAL,
            command=self.image_canvas.xview,
        )
        self.image_canvas.configure(
            xscrollcommand=image_x.set,
            yscrollcommand=image_y.set,
        )
        self.image_canvas.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=(12, 0))
        image_y.grid(row=0, column=1, sticky="ns", pady=(12, 0))
        image_x.grid(row=1, column=0, sticky="ew", padx=(12, 0))
        tk.Label(
            image_frame,
            textvariable=self.image_var,
            anchor="w",
            background="#202020",
            foreground="#e8e8e8",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))
        body.add(image_frame, minsize=360)

        text_frame = tk.Frame(body)
        tk.Label(
            text_frame,
            text="ARC Frame",
            anchor="w",
            font=("Consolas", 10, "bold"),
        ).pack(fill=tk.X, padx=8, pady=(8, 0))
        self.arc_text = tk.Text(
            text_frame,
            wrap=tk.NONE,
            font=("Consolas", 14),
            height=20,
            width=36,
        )
        self.arc_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.arc_text.configure(state=tk.DISABLED)
        body.add(text_frame, minsize=300)

        footer = tk.Frame(self.root)
        footer.pack(fill=tk.X)
        tk.Label(footer, textvariable=self.status_var, anchor="w").pack(
            fill=tk.X, padx=10
        )
        tk.Label(footer, textvariable=self.detail_var, anchor="w").pack(
            fill=tk.X, padx=10
        )
        self.event_text = tk.Text(
            self.root,
            height=5,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.event_text.pack(fill=tk.X, padx=10, pady=(4, 10))
        self.event_text.configure(state=tk.DISABLED)

    def render(self, steps: int, frame_data: Any) -> None:
        self._post(("render", int(steps), frame_data))

    def push_event(self, message: str) -> None:
        cleaned = " ".join(str(message).split())
        if cleaned:
            self._post(("event", cleaned))

    def set_status(self, message: str) -> None:
        self._post(("status", str(message).strip()))

    def set_detail(self, message: str) -> None:
        self._post(("detail", str(message).strip()))

    def run_engine(self, target: Callable[[], None]) -> None:
        if self._closed:
            return
        self._engine_thread = threading.Thread(
            target=self._run_engine_target,
            args=(target,),
            daemon=True,
        )
        self._engine_thread.start()
        self.root.after(self.ui_poll_ms, self._drain_messages)
        self.root.mainloop()
        if self._engine_error is not None:
            raise self._engine_error

    def close(self) -> None:
        self._post(("close",))

    def _run_engine_target(self, target: Callable[[], None]) -> None:
        try:
            target()
        except BaseException as exc:
            self._engine_error = exc
        finally:
            self._post(("close",))

    def _post(self, message: tuple) -> None:
        if self._closed:
            return
        if isinstance(self._messages, list):
            self._messages.append(message)
        else:
            self._messages.put(message)

    def _drain_messages(self, *, reschedule: bool = True) -> None:
        latest_render = None
        close_requested = False
        for message in self._pop_messages():
            kind = message[0]
            if kind == "render":
                latest_render = message
            elif kind == "event":
                self._apply_event(message[1])
            elif kind == "status":
                self._apply_status(message[1])
            elif kind == "detail":
                self._apply_detail(message[1])
            elif kind == "close":
                close_requested = True

        if latest_render is not None:
            self._apply_render(latest_render[1], latest_render[2])

        if close_requested:
            self._close_ui()
            return

        if reschedule and not self._closed:
            self.root.after(self.ui_poll_ms, self._drain_messages)

    def _pop_messages(self) -> list[tuple]:
        if isinstance(self._messages, list):
            messages = list(self._messages)
            self._messages.clear()
            return messages

        messages = []
        while True:
            try:
                messages.append(self._messages.get_nowait())
            except Empty:
                return messages

    def _apply_render(self, steps: int, frame_data: Any) -> None:
        self.step = int(steps)
        state = getattr(frame_data, "state", "")
        self.state = getattr(state, "name", str(state or "UNKNOWN"))
        self.levels_completed = int(getattr(frame_data, "levels_completed", 0))
        self.win_levels = int(getattr(frame_data, "win_levels", 0))
        action_input = getattr(frame_data, "action_input", None)
        action_id = getattr(action_input, "id", "") if action_input else ""
        self.last_action = getattr(action_id, "name", str(action_id or ""))

        self._set_arc_text(format_arc_frame(getattr(frame_data, "frame", []) or []))
        self._set_png(getattr(frame_data, "rendered_frame", None))
        self._refresh_labels()

    def _apply_event(self, cleaned: str) -> None:
        self.events.append(cleaned)
        self.events = self.events[-self.max_events :]
        self._set_events()

    def _apply_status(self, message: str) -> None:
        self.status = message
        self._refresh_labels()

    def _apply_detail(self, message: str) -> None:
        self.detail = message
        self._refresh_labels()

    def _close_ui(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError:
            pass

    def _set_arc_text(self, text: str) -> None:
        self.arc_text.configure(state=tk.NORMAL)
        self.arc_text.delete("1.0", tk.END)
        self.arc_text.insert("1.0", text)
        self.arc_text.configure(state=tk.DISABLED)

    def _set_png(self, rendered_frame: Any) -> None:
        payload = extract_png_base64(rendered_frame)
        if payload is None:
            self._photo = None
            self._clear_canvas_image()
            self.image_var.set("No PNG frame yet")
            return
        self._photo = self._make_photo(payload)
        width = int(self._photo.width())
        height = int(self._photo.height())
        self._set_canvas_image()
        self.image_canvas.configure(scrollregion=(0, 0, width, height))
        self.image_var.set(f"PNG {width}x{height}")

    def _make_photo(self, payload: str) -> tk.PhotoImage:
        return tk.PhotoImage(data=payload)

    def _set_canvas_image(self) -> None:
        self.image_canvas.delete("frame-image")
        self.image_canvas.create_image(
            0,
            0,
            anchor=tk.NW,
            image=self._photo,
            tags=("frame-image",),
        )

    def _clear_canvas_image(self) -> None:
        self.image_canvas.delete("frame-image")
        self.image_canvas.configure(scrollregion=(0, 0, 0, 0))

    def _set_events(self) -> None:
        self.event_text.configure(state=tk.NORMAL)
        self.event_text.delete("1.0", tk.END)
        self.event_text.insert("1.0", "\n".join(f"- {event}" for event in self.events))
        self.event_text.configure(state=tk.DISABLED)

    def _refresh_labels(self) -> None:
        last_action = f" | Last action: {self.last_action}" if self.last_action else ""
        self.header_var.set(
            f"Game: {self.game_id} | Mode: {self.mode} | Turn: {self.step} | "
            f"State: {self.state} | Levels: {self.levels_completed}/{self.win_levels}"
            f"{last_action}"
        )
        self.status_var.set(self.status)
        self.detail_var.set(self.detail or self.controls)
