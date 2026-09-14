from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path
from typing import Any

from client.arc.arcade_env import ArcadeEnv
from client.arc.base_env import BaseEnv
from client.arc.types import FrameData, GameAction, RenderedFrame
from avo.core.framework import Action, Comparison, Observation


def _similarity(expected: Any, actual: Any) -> float:
    if expected == actual:
        return 1.0
    if (
        isinstance(expected, list)
        and isinstance(actual, list)
        and expected
        and len(expected) == len(actual)
    ):
        pairs = list(zip(expected, actual))
        return sum(_similarity(left, right) for left, right in pairs) / len(pairs)
    return 0.0


class PuzzleScriptEnvironment:
    """Maps the ARC-compatible PuzzleScript surface into the generic AVO contract."""

    def __init__(self, environment: BaseEnv) -> None:
        self.environment = environment
        self._rendered_frame_output_dir: Path | None = None
        self._rendered_frame_sequence = 0

    def set_rendered_frame_output_dir(self, output_dir: str | Path) -> None:
        self._rendered_frame_output_dir = Path(output_dir).resolve()
        self._rendered_frame_output_dir.mkdir(parents=True, exist_ok=True)

    def _save_rendered_frame(
        self, rendered_frame: RenderedFrame | None
    ) -> dict[str, Any] | None:
        if rendered_frame is None or self._rendered_frame_output_dir is None:
            return None
        prefix = "data:image/png;base64,"
        if (
            rendered_frame.mime_type != "image/png"
            or not rendered_frame.data_url.startswith(prefix)
        ):
            return None
        try:
            png = base64.b64decode(rendered_frame.data_url[len(prefix) :], validate=True)
        except (ValueError, binascii.Error):
            return None
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            return None

        self._rendered_frame_sequence += 1
        filename = f"observation_{self._rendered_frame_sequence:06d}.png"
        target = self._rendered_frame_output_dir / filename
        target.write_bytes(png)
        return {
            "mime_type": rendered_frame.mime_type,
            "path": str(target),
            "artifact_path": target.relative_to(
                self._rendered_frame_output_dir.parent
            ).as_posix(),
            "width": rendered_frame.width,
            "height": rendered_frame.height,
            "sha256": hashlib.sha256(png).hexdigest(),
        }

    @staticmethod
    def from_frame(
        frame: FrameData,
        rendered_frame: dict[str, Any] | None = None,
    ) -> Observation:
        metadata: dict[str, Any] = {"projection": frame.projection}
        if rendered_frame is not None:
            metadata["rendered_frame"] = rendered_frame
        return Observation(
            payload={"frame": frame.frame},
            status=frame.state.value,
            progress={
                "levels_completed": frame.levels_completed,
                "win_levels": frame.win_levels,
            },
            available_actions=tuple(action.name for action in frame.available_actions),
            metadata=metadata,
        )

    def _observation(self, frame: FrameData) -> Observation:
        return self.from_frame(frame, self._save_rendered_frame(frame.rendered_frame))

    def reset(self) -> Observation:
        return self._observation(self.environment.reset())

    def step(self, action: Action) -> Observation:
        try:
            game_action = GameAction[action.id]
        except KeyError as exc:
            raise ValueError(f"Unknown PuzzleScript action: {action.id}") from exc
        return self._observation(self.environment.step(game_action, dict(action.data)))

    def save_state(self) -> str:
        method = getattr(self.environment, "save_state", None)
        if method is None:
            raise RuntimeError("PuzzleScript backend does not support state checkpoints")
        return str(method())

    def restore_state(self, token: str) -> Observation:
        method = getattr(self.environment, "restore_state", None)
        if method is None:
            raise RuntimeError("PuzzleScript backend does not support state checkpoints")
        return self._observation(method(token))

    def compare(self, expected: Observation, actual: Observation) -> Comparison:
        payload_score = _similarity(expected.payload, actual.payload)
        status_score = float(expected.status == actual.status)
        progress_score = float(expected.progress == actual.progress)
        return Comparison(
            exact=payload_score == 1 and status_score == 1 and progress_score == 1,
            prospective_accuracy=payload_score,
            status_accuracy=status_score,
            progress_accuracy=progress_score,
            details={
                "expected_fingerprint": expected.fingerprint,
                "actual_fingerprint": actual.fingerprint,
            },
        )
