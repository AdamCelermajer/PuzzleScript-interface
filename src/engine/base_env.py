from abc import ABC, abstractmethod

from engine.types import FrameData, GameAction


class BaseEnv(ABC):
    """Abstract interface for all grid-based environments."""

    @abstractmethod
    def reset(self) -> FrameData:
        """Reset the environment to its initial state and return the first FrameData."""

    @abstractmethod
    def step(self, action: GameAction) -> FrameData:
        """Apply an action to the environment and return the resulting FrameData."""
