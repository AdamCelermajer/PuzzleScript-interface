from __future__ import annotations

from client.arc.types import FrameData

from .model import DEFAULT_SYMBOL_MAP, SymbolFrame


class SymbolPerceiver:
    def __init__(self, symbol_map: dict[int, str] | None = None) -> None:
        self.symbol_map = dict(symbol_map or DEFAULT_SYMBOL_MAP)

    def from_grid(self, grid: list[list[int]]) -> SymbolFrame:
        return SymbolFrame.from_grid(grid, self.symbol_map)

    def perceive(self, frame_data: FrameData) -> SymbolFrame:
        return SymbolFrame.from_frame_data(frame_data, self.symbol_map)

