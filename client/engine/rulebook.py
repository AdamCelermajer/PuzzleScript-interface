from __future__ import annotations

from client.engine.history import TransitionRecord
from client.engine.rules import RuleEntry, RuleLibrary
from client.engine.state import EngineState
from client.engine.types import GameAction


class EngineRulebook:
    """Rule-facing boundary around prediction, verification accounting, and storage."""

    def __init__(self, library: RuleLibrary) -> None:
        self.library = library

    def predict(self, before: EngineState, action: GameAction) -> list[EngineState]:
        return self.library.predict(before, action)

    def record_prediction_result(
        self,
        before: EngineState,
        action: GameAction,
        actual_after: EngineState,
        predictions: list[EngineState],
    ) -> None:
        self.library.record_prediction_result(
            before, action, actual_after, predictions
        )

    def record_observed_transition(self, record: TransitionRecord) -> RuleEntry:
        return self.library.record_transition(record)

    def known_rules_text(self) -> str:
        return self.library.known_rules_text()
