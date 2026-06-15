from __future__ import annotations

from client.engine.history import TransitionHistory, TransitionRecord
from client.engine.state import EngineState
from client.engine.types import GameAction


class EngineMemory:
    """Persistent evidence boundary for observed state/action/state transitions."""

    def __init__(self, history: TransitionHistory) -> None:
        self.history = history

    def record_transition(
        self, before: EngineState, action: GameAction, after: EngineState
    ) -> TransitionRecord:
        return self.history.add(before, action, after)

    def all(self) -> list[TransitionRecord]:
        return self.history.all()

    def recent(self, limit: int) -> list[TransitionRecord]:
        return self.history.recent(limit)

    def action_count(self, before: EngineState, action: GameAction) -> int:
        return self.history.action_count(before, action)

    def global_action_count(self, action: GameAction) -> int:
        return self.history.global_action_count(action)
