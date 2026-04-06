"""
Python adapter to make PuzzleScript games run via the ARC-AGI environment interface.
"""
from dataclasses import dataclass, field
from enum import Enum
import requests

from engine.types import GameAction, GameState, ActionInput, FrameData
from envs.base_env import BaseEnv

REQUEST_TIMEOUT = 30  # seconds

class PuzzleScriptEnv(BaseEnv):
    def __init__(self, game_name: str, server_url: str = "http://localhost:3000"):
        self.game_name = game_name
        self.server_url = server_url
        self.session_id = None
        self.win_levels = 1
        self.legend = {}

    def _post(self, path: str, payload: dict) -> dict:
        """POST with timeout and status validation."""
        resp = requests.post(f"{self.server_url}{path}", json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

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
        resp = self._post("/init", {"gameName": self.game_name})
        if "sessionId" not in resp:
            raise Exception(f"Failed to init game: {resp}")
        self.session_id = resp["sessionId"]
        return self._parse_response(resp, None, full_reset=True)

    def step(self, action: GameAction) -> FrameData:
        if not self.session_id:
            return self.reset()
        if action == GameAction.RESET:
            resp = self._post("/action", {"sessionId": self.session_id, "action": "RESET"})
            return self._parse_response(resp, action, full_reset=True)
            
        action_name = action.name
        resp = self._post("/action", {"sessionId": self.session_id, "action": action_name})
        return self._parse_response(resp, action, full_reset=False)
