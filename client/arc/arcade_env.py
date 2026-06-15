import os
from types import SimpleNamespace

import requests
from arc_agi import Arcade, OperationMode
from arcengine import GameAction as ArcGameAction, GameState as ArcGameState

from client.arc.base_env import BaseEnv
from client.arc.types import (
    ActionInput,
    FrameData,
    GameAction,
    GameState,
    RenderedFrame,
)


def _to_namespace(value):
    if isinstance(value, dict):
        return SimpleNamespace(
            **{key: _to_namespace(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


def _is_official_arc_url(url: str) -> bool:
    return "three.arcprize.org" in str(url or "").strip().lower()


class LocalArcEnvironmentWrapper:
    """Direct local ARC-compatible HTTP wrapper that preserves extension fields."""

    def __init__(
        self,
        game_id: str,
        base_url: str,
        api_key: str,
        http_session=None,
    ) -> None:
        self.game_id = game_id
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key, "Accept": "application/json"}
        self._session = http_session or requests.Session()
        self.scorecard_id = self._open_scorecard()
        self.guid: str | None = None

    def _request(self, method: str, path: str, payload: dict | None = None):
        response = self._session.request(
            method,
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
            timeout=45,
        )
        response.raise_for_status()
        return response.json()

    def _open_scorecard(self) -> str:
        payload = self._request("POST", "/api/scorecard/open", {})
        return str(payload["card_id"])

    def reset(self):
        payload = {"card_id": self.scorecard_id, "game_id": self.game_id}
        if self.guid:
            payload["guid"] = self.guid
        frame = self._request("POST", "/api/cmd/RESET", payload)
        self.guid = str(frame.get("guid") or self.guid or "")
        return _to_namespace(frame)

    def step(self, action: GameAction, data: dict | None = None):
        if not self.guid:
            raise RuntimeError("Cannot step before reset")
        payload = {"game_id": self.game_id, "guid": self.guid}
        if data:
            payload.update(data)
        frame = self._request("POST", f"/api/cmd/{action.name}", payload)
        return _to_namespace(frame)


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
        http_session=None,
    ) -> None:
        self.game_id = game_id
        self.backend_url = backend_url
        self.api_key = api_key if api_key is not None else os.getenv("ARC_API_KEY", "")
        self.render_mode = render_mode
        self.renderer = renderer
        self._render_step = 0
        self.arcade = None
        if arcade_factory is Arcade and not _is_official_arc_url(self.backend_url):
            self._env = LocalArcEnvironmentWrapper(
                self.game_id,
                self.backend_url,
                self.api_key,
                http_session=http_session,
            )
        else:
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

    def _convert_state(self, state) -> GameState:
        normalized = getattr(state, "name", str(state or "")).upper()
        if state == ArcGameState.WIN or normalized == "WIN":
            return GameState.WIN
        if state == ArcGameState.GAME_OVER or normalized == "GAME_OVER":
            return GameState.GAME_OVER
        return GameState.PLAYING

    def _convert_action(self, action_value) -> GameAction:
        if isinstance(action_value, GameAction):
            return action_value
        if hasattr(action_value, "name"):
            return GameAction[str(getattr(action_value, "name"))]
        return GameAction(int(action_value))

    def _convert_rendered_frame(self, rendered_frame) -> RenderedFrame | None:
        if not rendered_frame:
            return None
        if isinstance(rendered_frame, RenderedFrame):
            return rendered_frame
        if isinstance(rendered_frame, dict):
            get_value = rendered_frame.get
        else:
            get_value = lambda key, default=None: getattr(
                rendered_frame, key, default
            )

        mime_type = get_value("mime_type")
        data_url = get_value("data_url")
        if not mime_type or not data_url:
            return None
        return RenderedFrame(
            mime_type=str(mime_type),
            data_url=str(data_url),
            width=get_value("width"),
            height=get_value("height"),
        )

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
            projection=getattr(frame_data, "projection", {}) or {},
            rendered_frame=self._convert_rendered_frame(
                getattr(frame_data, "rendered_frame", None)
            ),
        )

    def reset(self) -> FrameData:
        frame_data = self._env.reset()
        if frame_data is None:
            raise RuntimeError(f"Failed to reset ARC environment {self.game_id}")
        self._render_frame(frame_data)
        return self._convert_frame(frame_data)

    def step(self, action: GameAction, data: dict | None = None) -> FrameData:
        runtime_action = (
            action
            if isinstance(self._env, LocalArcEnvironmentWrapper)
            else ArcGameAction[action.name]
        )
        frame_data = self._env.step(runtime_action, data=data)
        if frame_data is None:
            raise RuntimeError(
                f"Failed to step ARC environment {self.game_id} with {action.name}"
            )
        self._render_frame(frame_data)
        return self._convert_frame(frame_data)
