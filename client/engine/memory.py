from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from client.engine.perception import EngineState
from client.arc.types import GameAction


@dataclass(frozen=True)
class StateNode:
    id: str
    state: EngineState
    kind: str = "state"

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "StateNode":
        return cls(id=str(data["id"]), state=EngineState.from_data(data["state"]))

    def to_data(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "state": self.state.to_data()}


@dataclass(frozen=True)
class ActionEdge:
    id: str
    action: GameAction
    before_id: str
    after_id: str
    kind: str = "action"

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "ActionEdge":
        return cls(
            id=str(data["id"]),
            action=GameAction[str(data["action"])],
            before_id=str(data["before_id"]),
            after_id=str(data["after_id"]),
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "action": self.action.name,
            "before_id": self.before_id,
            "after_id": self.after_id,
        }


TimelineItem = StateNode | ActionEdge


@dataclass(frozen=True)
class TransitionRecord:
    """Derived state/action/state evidence view over the canonical timeline."""

    id: str
    before: EngineState
    action: GameAction
    after: EngineState

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "before": self.before.to_data(),
            "action": self.action.name,
            "after": self.after.to_data(),
        }


class EngineMemory:
    """Persistent timeline of perceived state/action/state evidence."""

    def __init__(self, path: str | Path | object, load_existing: bool = True) -> None:
        self.path = Path(getattr(path, "path", path))
        self.timeline: list[TimelineItem] = []
        self._transitions: list[TransitionRecord] = []
        if load_existing:
            self._load()

    def append_initial_state(self, state: EngineState) -> StateNode:
        if self.timeline:
            return self._state_nodes()[-1]
        node = StateNode(id=self._new_state_id(), state=state)
        self.timeline.append(node)
        self._append_jsonl(node.to_data())
        return node

    def append_state(self, state: EngineState) -> StateNode:
        if not self.timeline:
            return self.append_initial_state(state)
        current = self._state_nodes()[-1]
        if current.state == state and current.state.image == state.image:
            return current
        node = StateNode(id=self._new_state_id(), state=state)
        self.timeline.append(node)
        self._append_jsonl(node.to_data())
        return node

    def append_action_result(
        self, action: GameAction, after_state: EngineState
    ) -> TransitionRecord:
        if not self.timeline:
            raise ValueError("Cannot append action result before initial state")

        before_node = self._state_nodes()[-1]
        after_node = StateNode(id=self._new_state_id(), state=after_state)
        edge = ActionEdge(
            id=self._new_action_id(),
            action=action,
            before_id=before_node.id,
            after_id=after_node.id,
        )
        self.timeline.extend([edge, after_node])
        self._append_jsonl(edge.to_data())
        self._append_jsonl(after_node.to_data())
        record = self._record_from_nodes(before_node, edge, after_node)
        self._transitions.append(record)
        return record

    def record_transition(
        self, before: EngineState, action: GameAction, after: EngineState
    ) -> TransitionRecord:
        if not self.timeline:
            self.append_initial_state(before)
        elif self.current_state() != before:
            node = StateNode(id=self._new_state_id(), state=before)
            self.timeline.append(node)
            self._append_jsonl(node.to_data())
        return self.append_action_result(action, after)

    def current_state(self) -> EngineState:
        nodes = self._state_nodes()
        if not nodes:
            raise ValueError("Memory has no current state")
        return nodes[-1].state

    def all(self) -> list[TransitionRecord]:
        return list(self._transitions)

    def recent(self, limit: int) -> list[TransitionRecord]:
        return self.recent_transitions(limit)

    def recent_transitions(self, limit: int) -> list[TransitionRecord]:
        return self._transitions[-max(0, int(limit)) :]

    def transition_by_id(self, record_id: str) -> TransitionRecord | None:
        return next(
            (record for record in self._transitions if record.id == record_id),
            None,
        )

    def latest_visual_context(self) -> tuple[str, list[str]]:
        if not self._transitions:
            return "", []
        record = self._transitions[-1]
        lines = [
            "Last memory transition:",
            f"{record.id}: {record.action.name}",
            f"Before:\n{self._rows(record.before)}",
            f"After:\n{self._rows(record.after)}",
        ]
        return "\n".join(lines), self.transition_images(record)

    def available_images(self) -> list[str]:
        _text, images = self.latest_visual_context()
        if images:
            return images
        try:
            current = self.current_state()
        except ValueError:
            return []
        return [current.image.data_url] if current.image else []

    def transition_images(self, record: TransitionRecord) -> list[str]:
        urls = []
        if record.before.image is not None:
            urls.append(record.before.image.data_url)
        if record.after.image is not None:
            urls.append(record.after.image.data_url)
        return [url for url in urls if url]

    def recent_context(self, limit: int = 1) -> str:
        lines = []
        for record in self.recent_transitions(limit):
            lines.append(
                f"{record.id}: {record.action.name}\n"
                f"Before:\n{self._rows(record.before)}\n"
                f"After:\n{self._rows(record.after)}"
            )
        return "\n\n".join(lines)

    def action_count(self, before: EngineState, action: GameAction) -> int:
        return sum(
            1
            for record in self._transitions
            if record.before == before and record.action == action
        )

    def global_action_count(self, action: GameAction) -> int:
        return sum(1 for record in self._transitions if record.action == action)

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            kind = data.get("kind")
            if kind == "state":
                self.timeline.append(StateNode.from_data(data))
            elif kind == "action":
                self.timeline.append(ActionEdge.from_data(data))
        self._rebuild_transitions()

    def _append_jsonl(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(data) + "\n")

    def _rebuild_transitions(self) -> None:
        nodes = {item.id: item for item in self.timeline if isinstance(item, StateNode)}
        records = []
        for item in self.timeline:
            if not isinstance(item, ActionEdge):
                continue
            before = nodes.get(item.before_id)
            after = nodes.get(item.after_id)
            if before is None or after is None:
                continue
            records.append(self._record_from_nodes(before, item, after))
        self._transitions = records

    def _record_from_nodes(
        self, before: StateNode, edge: ActionEdge, after: StateNode
    ) -> TransitionRecord:
        return TransitionRecord(
            id=f"T{int(edge.id[1:]):06d}",
            before=before.state,
            action=edge.action,
            after=after.state,
        )

    def _state_nodes(self) -> list[StateNode]:
        return [item for item in self.timeline if isinstance(item, StateNode)]

    def _new_state_id(self) -> str:
        return f"S{len(self._state_nodes()) + 1:06d}"

    def _new_action_id(self) -> str:
        return f"A{len(self._transitions) + 1:06d}"

    def _rows(self, state: EngineState) -> str:
        return "\n".join(state.rows())
