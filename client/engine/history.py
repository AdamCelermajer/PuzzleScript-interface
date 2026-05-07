from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from client.engine.state import EngineState
from client.engine.types import GameAction


@dataclass(frozen=True)
class TransitionRecord:
    id: str
    before: EngineState
    action: GameAction
    after: EngineState

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "TransitionRecord":
        return cls(
            id=str(data["id"]),
            before=EngineState.from_data(data["before"]),
            action=GameAction[str(data["action"])],
            after=EngineState.from_data(data["after"]),
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "before": self.before.to_data(),
            "action": self.action.name,
            "after": self.after.to_data(),
        }


class TransitionHistory:
    """Append-only state/action/state evidence store."""

    def __init__(self, path: str | Path, load_existing: bool = True) -> None:
        self.path = Path(path)
        self._records: list[TransitionRecord] = []
        if load_existing:
            self._load()

    def add(
        self, before: EngineState, action: GameAction, after: EngineState
    ) -> TransitionRecord:
        record = TransitionRecord(
            id=f"T{len(self._records) + 1:06d}",
            before=before,
            action=action,
            after=after,
        )
        self._records.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record.to_data()) + "\n")
        return record

    def all(self) -> list[TransitionRecord]:
        return list(self._records)

    def recent(self, limit: int) -> list[TransitionRecord]:
        return self._records[-max(0, int(limit)) :]

    def action_count(self, before: EngineState, action: GameAction) -> int:
        return sum(
            1
            for record in self._records
            if record.before == before and record.action == action
        )

    def global_action_count(self, action: GameAction) -> int:
        return sum(1 for record in self._records if record.action == action)

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            self._records.append(TransitionRecord.from_data(json.loads(line)))
