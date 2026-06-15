from __future__ import annotations

import base64
import binascii
import html
from dataclasses import dataclass
from pathlib import Path

from client.engine.types import FrameData, GameAction


@dataclass(frozen=True)
class VisualTransition:
    """The last real before/action/after transition, including optional images."""

    before_frame: FrameData
    action: GameAction
    after_frame: FrameData

    def image_data_urls(self) -> list[str]:
        urls = [
            self._data_url(self.before_frame),
            self._data_url(self.after_frame),
        ]
        return [url for url in urls if url]

    def prompt_text(self) -> str:
        return (
            "Last visual transition:\n"
            f"Frame -2:\n{self._rows(self.before_frame)}\n\n"
            f"Action: {self.action.name}\n\n"
            f"Frame -1:\n{self._rows(self.after_frame)}"
        )

    def _data_url(self, frame: FrameData) -> str:
        rendered_frame = getattr(frame, "rendered_frame", None)
        return str(getattr(rendered_frame, "data_url", "") or "")

    def _rows(self, frame: FrameData) -> str:
        if not frame.frame:
            return ""
        grid = frame.frame[-1]
        return "\n".join(" ".join(str(value) for value in row) for row in grid)


def dump_visual_transition(
    visual_transition: VisualTransition, directory: str | Path
) -> Path:
    """Write the latest visual transition to a temporary inspection directory."""

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / "latest-context.txt").write_text(
        visual_transition.prompt_text(),
        encoding="utf-8",
    )
    _write_data_url(
        visual_transition.before_frame,
        target / "latest-before",
    )
    _write_data_url(
        visual_transition.after_frame,
        target / "latest-after",
    )
    _write_preview_html(visual_transition, target)
    return target


def _write_data_url(frame: FrameData, stem: Path) -> None:
    rendered_frame = getattr(frame, "rendered_frame", None)
    data_url = str(getattr(rendered_frame, "data_url", "") or "")
    if not data_url:
        return
    mime_type = str(getattr(rendered_frame, "mime_type", "") or "")
    extension = _extension(mime_type)
    if "," not in data_url:
        stem.with_suffix(".txt").write_text(data_url, encoding="utf-8")
        return
    header, payload = data_url.split(",", 1)
    if ";base64" not in header:
        stem.with_suffix(".txt").write_text(payload, encoding="utf-8")
        return
    try:
        stem.with_suffix(extension).write_bytes(base64.b64decode(payload))
    except (ValueError, binascii.Error):
        stem.with_suffix(".txt").write_text(data_url, encoding="utf-8")


def _extension(mime_type: str) -> str:
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/webp":
        return ".webp"
    return ".png"


def _write_preview_html(visual_transition: VisualTransition, target: Path) -> None:
    before_name = f"latest-before{_extension_for_frame(visual_transition.before_frame)}"
    after_name = f"latest-after{_extension_for_frame(visual_transition.after_frame)}"
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Latest LLM Visual Context</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; }}
    .frames {{ display: flex; gap: 24px; align-items: flex-start; }}
    img {{
      width: 320px;
      height: auto;
      image-rendering: pixelated;
      border: 1px solid #bbb;
      background: #eee;
    }}
    pre {{ white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>Latest LLM Visual Context</h1>
  <p>Action: {visual_transition.action.name}</p>
  <div class="frames">
    <section>
      <h2>Frame -2</h2>
      <img src="{before_name}" alt="Frame before action">
    </section>
    <section>
      <h2>Frame -1</h2>
      <img src="{after_name}" alt="Frame after action">
    </section>
  </div>
  <h2>Text Context</h2>
  <pre>{html.escape(visual_transition.prompt_text())}</pre>
</body>
</html>
"""
    (target / "latest-preview.html").write_text(html_doc, encoding="utf-8")


def _extension_for_frame(frame: FrameData) -> str:
    rendered_frame = getattr(frame, "rendered_frame", None)
    mime_type = str(getattr(rendered_frame, "mime_type", "") or "")
    return _extension(mime_type)
