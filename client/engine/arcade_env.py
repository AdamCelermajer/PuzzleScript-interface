import os

from arc_agi import Arcade, OperationMode
from arcengine import GameAction as ArcGameAction, GameState as ArcGameState

from client.engine.base_env import BaseEnv
from client.engine.types import ActionInput, FrameData, GameAction, GameState


class ArcadeEnv(BaseEnv):
    """Thin adapter from ARC toolkit environments to the local engine types."""

    def __init__(
        self,
        game_id: str,
        backend_url: str = "https://three.arcprize.org",
        api_key: str | None = None,
        render_mode: str | None = None,
        renderer=None,
        arcade_factory=Arcade,
    ) -> None:
        self.game_id = game_id
        self.backend_url = backend_url
        self.api_key = api_key if api_key is not None else os.getenv("ARC_API_KEY", "")
        self.render_mode = render_mode
        self.renderer = renderer
        self._render_step = 0
        self.arcade = arcade_factory(
            operation_mode=OperationMode.ONLINE,
            arc_base_url=self.backend_url,
            arc_api_key=self.api_key,
        )
        self._env = self.arcade.make(
            self.game_id,
            render_mode=self.render_mode,
        )
        if self._env is None:
            raise ValueError(f"Could not create ARC environment for {self.game_id}")
        self.session_id = self.game_id

    def _render_frame(self, frame_data) -> None:
        if self.renderer is None or frame_data is None:
            return
        self._render_step += 1
        self.renderer(self._render_step, frame_data)

    def _convert_state(self, state: ArcGameState) -> GameState:
        if state == ArcGameState.WIN:
            return GameState.WIN
        if state == ArcGameState.GAME_OVER:
            return GameState.GAME_OVER
        return GameState.PLAYING

    def _convert_action(self, action_value) -> GameAction:
        if isinstance(action_value, GameAction):
            return action_value
        if hasattr(action_value, "name"):
            return GameAction[str(getattr(action_value, "name"))]
        return GameAction(int(action_value))

    def _convert_frame(self, frame_data) -> FrameData:
        frame_layers = [
            layer.tolist() if hasattr(layer, "tolist") else layer
            for layer in getattr(frame_data, "frame", [])
        ]
        available_actions = []
        for action_id in getattr(frame_data, "available_actions", []):
            try:
                available_actions.append(self._convert_action(action_id))
            except (KeyError, ValueError, TypeError):
                continue

        action_input_data = getattr(frame_data, "action_input", None)
        action_input = (
            ActionInput(
                action=self._convert_action(getattr(action_input_data, "id", 0)),
                data=getattr(action_input_data, "data", {}) or {},
            )
            if action_input_data is not None
            else ActionInput(action=GameAction.RESET)
        )

        return FrameData(
            frame=frame_layers,
            state=self._convert_state(
                getattr(frame_data, "state", ArcGameState.NOT_FINISHED)
            ),
            levels_completed=int(getattr(frame_data, "levels_completed", 0)),
            game_id=getattr(frame_data, "game_id", self.game_id),
            win_levels=int(getattr(frame_data, "win_levels", 0)),
            guid=getattr(frame_data, "guid", "") or "",
            full_reset=bool(getattr(frame_data, "full_reset", False)),
            available_actions=available_actions,
            action_input=action_input,
            legend={},
        )

    def reset(self) -> FrameData:
        frame_data = self._env.reset()
        if frame_data is None:
            raise RuntimeError(f"Failed to reset ARC environment {self.game_id}")
        self._render_frame(frame_data)
        return self._convert_frame(frame_data)

    def step(self, action: GameAction) -> FrameData:
        frame_data = self._env.step(ArcGameAction[action.name])
        if frame_data is None:
            raise RuntimeError(
                f"Failed to step ARC environment {self.game_id} with {action.name}"
            )
        self._render_frame(frame_data)
        return self._convert_frame(frame_data)
