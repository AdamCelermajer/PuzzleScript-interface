import base64
from types import SimpleNamespace

from client.screen_dashboard import ScreenDashboard, extract_png_base64, format_arc_frame


def test_format_arc_frame_uses_final_grid_as_ascii() -> None:
    formatted = format_arc_frame(
        [
            [[0, 1], [2, 3]],
            [[8, 9], [14, 15]],
        ]
    )

    assert formatted == "8 9\nE F"


def test_extract_png_base64_accepts_rendered_frame_data_url() -> None:
    payload = base64.b64encode(b"png bytes").decode("ascii")
    rendered_frame = SimpleNamespace(
        mime_type="image/png",
        data_url=f"data:image/png;base64,{payload}",
    )

    assert extract_png_base64(rendered_frame) == payload


def test_extract_png_base64_accepts_dict_rendered_frame() -> None:
    payload = base64.b64encode(b"png bytes").decode("ascii")

    assert (
        extract_png_base64(
            {
                "mime_type": "image/png",
                "data_url": f"data:image/png;base64,{payload}",
            }
        )
        == payload
    )


def test_extract_png_base64_rejects_missing_or_non_png_frame() -> None:
    assert extract_png_base64(None) is None
    assert (
        extract_png_base64(
            SimpleNamespace(mime_type="image/jpeg", data_url="data:image/jpeg;base64,x")
        )
        is None
    )


def test_render_enqueues_without_touching_tk_widgets() -> None:
    dashboard = ScreenDashboard.__new__(ScreenDashboard)
    dashboard._closed = False
    dashboard._messages = []

    dashboard.render(3, SimpleNamespace(frame=[[[1]]]))

    assert dashboard._messages == [("render", 3, SimpleNamespace(frame=[[[1]]]))]


def test_drain_messages_coalesces_render_updates() -> None:
    dashboard = ScreenDashboard.__new__(ScreenDashboard)
    dashboard._closed = False
    dashboard._messages = [
        ("render", 1, SimpleNamespace(frame=[[[1]]])),
        ("status", "working"),
        ("render", 2, SimpleNamespace(frame=[[[2]]])),
        ("event", "first"),
        ("render", 3, SimpleNamespace(frame=[[[3]]])),
    ]
    dashboard.events = []
    dashboard.max_events = 8
    applied: list[tuple[int, object]] = []
    statuses: list[str] = []
    events: list[str] = []
    dashboard._apply_render = lambda steps, frame_data: applied.append(
        (steps, frame_data)
    )
    dashboard._apply_status = lambda message: statuses.append(message)
    dashboard._apply_event = lambda message: events.append(message)
    dashboard._apply_detail = lambda message: None
    dashboard._close_ui = lambda: None

    dashboard._drain_messages(reschedule=False)

    assert [step for step, _frame in applied] == [3]
    assert statuses == ["working"]
    assert events == ["first"]


def test_set_png_updates_canvas_scroll_region_to_image_size() -> None:
    dashboard = ScreenDashboard.__new__(ScreenDashboard)
    dashboard.image_canvas = SimpleNamespace(
        calls=[],
        configure=lambda **kwargs: dashboard.image_canvas.calls.append(kwargs),
    )
    dashboard.image_var = SimpleNamespace(set=lambda _value: None)
    dashboard._photo = SimpleNamespace(width=lambda: 1080, height=lambda: 1260)
    dashboard._make_photo = lambda _payload: dashboard._photo
    dashboard._set_canvas_image = lambda: None

    payload = base64.b64encode(b"png bytes").decode("ascii")
    dashboard._set_png(
        SimpleNamespace(
            mime_type="image/png",
            data_url=f"data:image/png;base64,{payload}",
        )
    )

    assert {"scrollregion": (0, 0, 1080, 1260)} in dashboard.image_canvas.calls
