from __future__ import annotations

from client.engine.base_env import BaseEnv
from client.engine.types import FrameData, GameAction


class EnvironmentSurface:
    """Narrow runtime surface used by the engine loop."""

    def __init__(self, env: BaseEnv) -> None:
        self.env = env

    @property
    def session_id(self) -> str:
        return str(getattr(self.env, "session_id", "unknown"))

    def reset(self) -> FrameData:
        return self.env.reset()

    def step(self, action: GameAction) -> FrameData:
        return self.env.step(action)
