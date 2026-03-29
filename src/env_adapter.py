"""
Python adapter to make PuzzleScript games run via the ARC-AGI environment interface.
"""
from dataclasses import dataclass, field
from enum import Enum
import requests

class GameAction(Enum):
    RESET = 0
    ACTION1 = 1  # UP
    ACTION2 = 2  # DOWN
    ACTION3 = 3  # LEFT
    ACTION4 = 4  # RIGHT
    ACTION5 = 5  # ACTION/SPACE
    ACTION6 = 6  # CLICK (unused)

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
    legend: dict[int, str] = field(default_factory=dict)  # Our custom addition

class PuzzleScriptEnv:
    def __init__(self, game_name: str, server_url: str = "http://localhost:3000"):
        self.game_name = game_name
        self.server_url = server_url
        self.session_id = None
        self.win_levels = 1
        self.legend = {}
        
    def _parse_response(self, data: dict, action: GameAction, full_reset: bool = False) -> FrameData:
        self.legend = {int(k): v for k, v in data.get("legend", self.legend).items()}
        state_str = data.get("state", "PLAYING")
        state = GameState[state_str] if hasattr(GameState, state_str) else GameState.PLAYING
        self.win_levels = data.get("win_levels", self.win_levels)
        
        return FrameData(
            frame=data.get("frame", []),
            state=state,
            levels_completed=data.get("levels_completed", 0),
            game_id=self.game_name,
            win_levels=self.win_levels,
            guid=self.session_id,
            full_reset=full_reset,
            available_actions=[GameAction[a] for a in data.get("available_actions", [])],
            action_input=ActionInput(action=action) if action else None,
            legend=self.legend
        )

    def reset(self) -> FrameData:
        resp = requests.post(f"{self.server_url}/init", json={"gameName": self.game_name}).json()
        if "sessionId" not in resp:
            raise Exception(f"Failed to init game: {resp}")
        self.session_id = resp["sessionId"]
        return self._parse_response(resp, None, full_reset=True)

    def step(self, action: GameAction) -> FrameData:
        if not self.session_id:
            return self.reset()
        if action == GameAction.RESET:
            resp = requests.post(f"{self.server_url}/action", json={"sessionId": self.session_id, "action": "RESET"}).json()
            return self._parse_response(resp, action, full_reset=True)
            
        action_name = action.name
        resp = requests.post(f"{self.server_url}/action", json={"sessionId": self.session_id, "action": action_name}).json()
        return self._parse_response(resp, action, full_reset=False)
