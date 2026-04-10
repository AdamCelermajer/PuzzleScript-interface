from dataclasses import dataclass, field
from enum import Enum


class GameAction(Enum):
    RESET = 0
    ACTION1 = 1  # UP
    ACTION2 = 2  # DOWN
    ACTION3 = 3  # LEFT
    ACTION4 = 4  # RIGHT
    ACTION5 = 5  # ACTION/SPACE
    ACTION6 = 6  # CLICK (unused)
    ACTION7 = 7  # UNDO


class GameState(Enum):
    NOT_PLAYED = "NOT_PLAYED"
    PLAYING = "PLAYING"
    WIN = "WIN"
    GAME_OVER = "GAME_OVER"


@dataclass
class ActionInput:
    action: GameAction
    data: dict = field(default_factory=dict)


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
