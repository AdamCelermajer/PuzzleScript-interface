from dataclasses import dataclass, field
from enum import Enum


class GameAction(Enum):
    RESET = 0
    ACTION1 = 1
    ACTION2 = 2
    ACTION3 = 3
    ACTION4 = 4
    ACTION5 = 5
    ACTION6 = 6
    ACTION7 = 7


class GameState(Enum):
    NOT_PLAYED = "NOT_PLAYED"
    PLAYING = "PLAYING"
    WIN = "WIN"
    GAME_OVER = "GAME_OVER"


@dataclass
class ActionInput:
    action: GameAction
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RenderedFrame:
    mime_type: str
    data_url: str
    width: int | None = None
    height: int | None = None


@dataclass
class FrameData:
    frame: list[list[list[int]]]
    state: GameState
    levels_completed: int
    game_id: str
    win_levels: int
    guid: str
    full_reset: bool
    available_actions: list[GameAction]
    action_input: ActionInput
    legend: dict[int, str] = field(default_factory=dict)
    projection: dict = field(default_factory=dict)
    rendered_frame: RenderedFrame | None = None
