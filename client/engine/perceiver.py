from __future__ import annotations

from client.engine.state import EngineState
from client.engine.types import FrameData
from client.engine.utils import last_grid


class Perceiver:
    """Converts ARC/PuzzleScript observations into stable engine state."""

    def perceive(self, frame_data: FrameData) -> EngineState:
        grid = tuple(tuple(int(value) for value in row) for row in last_grid(frame_data.frame))
        return EngineState(
            grid=grid,
            state=frame_data.state,
            levels_completed=int(frame_data.levels_completed),
            win_levels=int(frame_data.win_levels),
            game_id=str(frame_data.game_id),
        )
