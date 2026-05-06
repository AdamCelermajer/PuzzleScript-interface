from __future__ import annotations

from client.engine.types import FrameData
from client.engine.utils import last_grid

from .model import HelpedFrame


class HelpedPerceiver:
    def __init__(self) -> None:
        pass

    def from_grid(self, grid: list[list[int]]) -> HelpedFrame:
        return HelpedFrame.from_grid(grid)

    def perceive(self, frame_data: FrameData) -> HelpedFrame:
        return self.from_grid(last_grid(frame_data.frame))
