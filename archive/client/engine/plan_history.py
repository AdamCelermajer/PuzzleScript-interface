from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from client.engine.memory import ActionEdge, EngineMemory


PLAN_HISTORY_VERSION = 1


def _transition_number(transition_id: str) -> int:
    digits = "".join(character for character in str(transition_id) if character.isdigit())
    return int(digits or 0)


def _transition_id(edge: ActionEdge) -> str:
    return f"T{_transition_number(edge.id):06d}"


def _action_names(value: Any) -> tuple[str, ...]:
    raw_actions = value if isinstance(value, list) else [value] if value else []
    return tuple(
        str(action).strip().upper()
        for action in raw_actions
        if str(action).strip()
    )


@dataclass(frozen=True)
class PlanChange:
    transition_id: str
    subgoal: str
    actions: tuple[str, ...]
    source: str = "explore_subgoal"
    origin: str = "runtime"

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "PlanChange":
        return cls(
            transition_id=str(data.get("transition_id", "")),
            subgoal=str(data.get("subgoal", "")).strip(),
            actions=_action_names(data.get("actions", [])),
            source=str(data.get("source", "explore_subgoal")),
            origin=str(data.get("origin", "runtime")),
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "subgoal": self.subgoal,
            "actions": list(self.actions),
            "source": self.source,
            "origin": self.origin,
        }


class PlanHistory:
    """Persistent log of points where the active subgoal plan changed."""

    def __init__(self, path: str | Path, *, create: bool = False) -> None:
        self.path = Path(path)
        self.changes: list[PlanChange] = []
        self._load()
        if create and not self.path.exists():
            self._save()

    def record_change(
        self,
        transition_id: str,
        subgoal: str,
        actions: list[str] | tuple[str, ...],
        *,
        source: str = "explore_subgoal",
        origin: str = "runtime",
    ) -> PlanChange | None:
        change = PlanChange(
            transition_id=str(transition_id),
            subgoal=str(subgoal).strip(),
            actions=_action_names(list(actions)),
            source=str(source),
            origin=str(origin),
        )
        if not change.transition_id or not change.subgoal or not change.actions:
            return None
        if any(item.transition_id == change.transition_id for item in self.changes):
            return None
        self.changes.append(change)
        self.changes.sort(key=lambda item: _transition_number(item.transition_id))
        self._save()
        return change

    def replay_steps(self, memory: EngineMemory) -> dict[str, dict[str, Any]]:
        """Map resulting state IDs to valid consecutive steps of a saved plan."""

        changes = {item.transition_id: item for item in self.changes}
        steps: dict[str, dict[str, Any]] = {}
        active: PlanChange | None = None
        next_index = 0
        for item in memory.timeline:
            if not isinstance(item, ActionEdge):
                continue
            transition_id = _transition_id(item)
            change = changes.get(transition_id)
            if change is not None:
                active = change
                next_index = 0
            elif active is None or item.decision_source != "active_plan":
                active = None
                continue
            if next_index >= len(active.actions):
                active = None
                continue
            if item.action.name != active.actions[next_index]:
                active = None
                continue
            steps[item.after_id] = {
                **active.to_data(),
                "step_index": next_index + 1,
                "total_steps": len(active.actions),
            }
            next_index += 1
            if next_index >= len(active.actions):
                active = None
        return steps

    def to_data(self) -> dict[str, Any]:
        return {
            "version": PLAN_HISTORY_VERSION,
            "changes": [item.to_data() for item in self.changes],
        }

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        raw_changes = data.get("changes", []) if isinstance(data, dict) else []
        self.changes = [
            PlanChange.from_data(item)
            for item in raw_changes
            if isinstance(item, dict)
        ]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(self.to_data(), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def _parsed_attempt(record: dict[str, Any]) -> dict[str, Any]:
    parsed = record.get("parsed_response")
    if isinstance(parsed, dict):
        return parsed
    raw = record.get("raw_response")
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _raw_plan_pairs(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    if not path.exists():
        return []
    pairs: list[tuple[str, tuple[str, ...]]] = []
    pending_subgoal = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        purpose = str(record.get("purpose", "")).strip().lower()
        data = _parsed_attempt(record)
        if "subgoal" in purpose or "subgoal" in data:
            candidate = str(data.get("subgoal", "")).strip()
            if candidate:
                pending_subgoal = candidate
        if "rule" in purpose:
            continue
        if "action" not in purpose and not any(
            key in data for key in ("plan", "actions")
        ):
            continue
        actions = _action_names(
            data.get("plan") or data.get("actions") or data.get("action")
        )
        subgoal = str(data.get("subgoal", "")).strip() or pending_subgoal
        if subgoal and actions:
            pairs.append((subgoal, actions))
            pending_subgoal = ""
    return pairs


def backfill_plan_history(
    plan_path: str | Path,
    llm_attempt_path: str | Path,
    memory: EngineMemory,
    *,
    create: bool = False,
) -> PlanHistory:
    history = PlanHistory(plan_path)
    if history.changes:
        return history

    edges = [item for item in memory.timeline if isinstance(item, ActionEdge)]
    cursor = 0
    for subgoal, actions in _raw_plan_pairs(Path(llm_attempt_path)):
        start = None
        for index in range(cursor, len(edges)):
            edge = edges[index]
            if (
                "explor" in edge.decision_source
                and edge.action.name == actions[0]
            ):
                start = index
                break
        if start is None:
            continue
        history.record_change(
            _transition_id(edges[start]),
            subgoal,
            actions,
            source=edges[start].decision_source or "explore_subgoal",
            origin="raw_log_backfill",
        )
        consumed = 1
        for offset, action in enumerate(actions[1:], start=1):
            edge_index = start + offset
            if edge_index >= len(edges):
                break
            edge = edges[edge_index]
            if edge.action.name != action or edge.decision_source != "active_plan":
                break
            consumed += 1
        cursor = start + consumed

    if create and not history.path.exists():
        history._save()
    return history
