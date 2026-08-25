from __future__ import annotations

from typing import Any

from client.arc.arcade_env import ArcadeEnv
from client.arc.base_env import BaseEnv
from client.arc.types import FrameData, GameAction
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

    @staticmethod
    def from_frame(frame: FrameData) -> Observation:
        return Observation(
            payload={"frame": frame.frame},
            status=frame.state.value,
            progress={
                "levels_completed": frame.levels_completed,
                "win_levels": frame.win_levels,
            },
            available_actions=tuple(action.name for action in frame.available_actions),
            metadata={"projection": frame.projection},
        )

    def reset(self) -> Observation:
        return self.from_frame(self.environment.reset())

    def step(self, action: Action) -> Observation:
        try:
            game_action = GameAction[action.id]
        except KeyError as exc:
            raise ValueError(f"Unknown PuzzleScript action: {action.id}") from exc
        return self.from_frame(self.environment.step(game_action, dict(action.data)))

    def save_state(self) -> str:
        method = getattr(self.environment, "save_state", None)
        if method is None:
            raise RuntimeError("PuzzleScript backend does not support state checkpoints")
        return str(method())

    def restore_state(self, token: str) -> Observation:
        method = getattr(self.environment, "restore_state", None)
        if method is None:
            raise RuntimeError("PuzzleScript backend does not support state checkpoints")
        return self.from_frame(method(token))

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
