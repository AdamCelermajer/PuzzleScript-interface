from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from client.engine.perception import EngineState
from client.arc.types import GameAction, GameState


@dataclass(frozen=True)
class CellCondition:
    dx: int
    dy: int
    value: int

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "CellCondition":
        _require_fields(data, ("dx", "dy", "value"))
        return cls(dx=int(data["dx"]), dy=int(data["dy"]), value=int(data["value"]))

    def to_data(self) -> dict[str, int]:
        return {"dx": self.dx, "dy": self.dy, "value": self.value}

    def matches(self, state: EngineState, anchor_x: int, anchor_y: int) -> bool:
        return state.cell(anchor_x + self.dx, anchor_y + self.dy) == self.value


@dataclass(frozen=True)
class CellEffect:
    dx: int
    dy: int
    value: int

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "CellEffect":
        _require_fields(data, ("dx", "dy", "value"))
        return cls(dx=int(data["dx"]), dy=int(data["dy"]), value=int(data["value"]))

    def to_data(self) -> dict[str, int]:
        return {"dx": self.dx, "dy": self.dy, "value": self.value}


@dataclass(frozen=True)
class GeneralizedRule:
    id: str
    action: str
    anchor: int
    conditions: tuple[CellCondition, ...]
    effects: tuple[CellEffect, ...]
    evidence_ids: tuple[str, ...]
    summary: str = ""
    contradictions: tuple[str, ...] = ()
    prediction_hits: int = 0
    prediction_failures: int = 0
    revision_count: int = 0
    result_state: str | None = None
    levels_completed: int | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "GeneralizedRule":
        if "logical_rule" in data:
            logical_rule = data["logical_rule"]
            _require_fields(data, ("ruleID", "logical_rule", "evidence"))
            _require_fields(logical_rule, ("action", "anchor", "conditions", "effects"))
            evidence = data.get("evidence", {})
            anchor = logical_rule["anchor"]
            anchor_value = anchor.get("value") if isinstance(anchor, dict) else anchor
            return cls(
                id=str(data["ruleID"]),
                action=_action_name(logical_rule["action"]),
                anchor=int(anchor_value),
                conditions=tuple(
                    CellCondition.from_data(_offset_item(item))
                    for item in logical_rule.get("conditions", [])
                ),
                effects=tuple(
                    CellEffect.from_data(_offset_item(item))
                    for item in logical_rule.get("effects", [])
                ),
                evidence_ids=tuple(str(item) for item in evidence.get("supports", [])),
                summary=str(data.get("natural_language", "")),
                contradictions=tuple(
                    str(item) for item in evidence.get("contradictions", [])
                ),
                prediction_hits=int(evidence.get("prediction_hits", 0)),
                prediction_failures=int(evidence.get("prediction_failures", 0)),
                revision_count=int(data.get("revision_count", 0)),
                result_state=(
                    str(logical_rule["result_state"])
                    if logical_rule.get("result_state") is not None
                    else None
                ),
                levels_completed=(
                    int(logical_rule["levels_completed"])
                    if logical_rule.get("levels_completed") is not None
                    else None
                ),
            )

        _require_fields(data, ("id", "action", "anchor", "conditions", "effects"))
        action = _action_name(data["action"])
        return cls(
            id=str(data["id"]),
            action=action,
            anchor=_anchor_value(data["anchor"]),
            conditions=tuple(
                CellCondition.from_data(_offset_item(item))
                for item in data.get("conditions", [])
            ),
            effects=tuple(
                CellEffect.from_data(_offset_item(item))
                for item in data.get("effects", [])
            ),
            evidence_ids=tuple(str(item) for item in data.get("evidence_ids", [])),
            summary=str(data.get("summary", "")),
            contradictions=tuple(
                str(item)
                for item in data.get("contradictions", data.get("failures", []))
            ),
            prediction_hits=int(data.get("prediction_hits", 0)),
            prediction_failures=int(data.get("prediction_failures", 0)),
            revision_count=int(data.get("revision_count", 0)),
            result_state=(
                str(data["result_state"]) if data.get("result_state") is not None else None
            ),
            levels_completed=(
                int(data["levels_completed"])
                if data.get("levels_completed") is not None
                else None
            ),
        )

    def to_data(self) -> dict[str, Any]:
        logical_rule: dict[str, Any] = {
            "action": self.action,
            "anchor": {"value": self.anchor},
            "conditions": [_logical_condition(item) for item in self.conditions],
            "effects": [_logical_effect(item) for item in self.effects],
        }
        if self.result_state is not None:
            logical_rule["result_state"] = self.result_state
        if self.levels_completed is not None:
            logical_rule["levels_completed"] = self.levels_completed
        return {
            "ruleID": self.id,
            "natural_language": self.summary,
            "logical_rule": logical_rule,
            "evidence": {
                "supports": list(self.evidence_ids),
                "contradictions": list(self.contradictions),
                "prediction_hits": self.prediction_hits,
                "prediction_failures": self.prediction_failures,
            },
            "revision_count": self.revision_count,
        }

    def predict(self, state: EngineState) -> list[EngineState]:
        predictions: list[EngineState] = []
        seen: set[EngineState] = set()
        for anchor_x, anchor_y in state.positions(self.anchor):
            if not all(
                condition.matches(state, anchor_x, anchor_y)
                for condition in self.conditions
            ):
                continue
            predicted = self._apply_effects(state, anchor_x, anchor_y)
            if predicted is None or predicted in seen:
                continue
            predictions.append(predicted)
            seen.add(predicted)
        return predictions

    def with_contradictions(self, contradictions: tuple[str, ...]) -> "GeneralizedRule":
        return replace(
            self,
            contradictions=contradictions,
            prediction_failures=self.prediction_failures + len(contradictions),
        )

    def with_id(self, rule_id: str) -> "GeneralizedRule":
        return replace(self, id=rule_id)

    def with_hit(self) -> "GeneralizedRule":
        return replace(self, prediction_hits=self.prediction_hits + 1)

    def with_contradiction(self, contradiction: str) -> "GeneralizedRule":
        return replace(
            self,
            contradictions=(*self.contradictions, contradiction),
            prediction_failures=self.prediction_failures + 1,
        )

    def revised_from(self, previous: "GeneralizedRule") -> "GeneralizedRule":
        return replace(
            self,
            id=previous.id,
            prediction_hits=previous.prediction_hits,
            prediction_failures=previous.prediction_failures,
            revision_count=previous.revision_count + 1,
        )

    def _apply_effects(
        self, state: EngineState, anchor_x: int, anchor_y: int
    ) -> EngineState | None:
        rows = [list(row) for row in state.grid]
        for effect in self.effects:
            x = anchor_x + effect.dx
            y = anchor_y + effect.dy
            if y < 0 or y >= len(rows) or x < 0 or x >= len(rows[y]):
                return None
            rows[y][x] = effect.value

        result_state = state.state
        if self.result_state:
            result_state = GameState(self.result_state)

        return EngineState(
            grid=tuple(tuple(row) for row in rows),
            state=result_state,
            levels_completed=(
                self.levels_completed
                if self.levels_completed is not None
                else state.levels_completed
            ),
            win_levels=state.win_levels,
            game_id=state.game_id,
        )


def candidate_rules_from_llm_json(data: dict[str, Any]) -> list[GeneralizedRule]:
    if not isinstance(data, dict):
        raise ValueError("LLM rule response must be a JSON object")
    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("LLM rule response field 'rules' must be a list")

    rules: list[GeneralizedRule] = []
    for index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"rule {index} must be an object")
        _require_fields(
            raw_rule,
            ("summary", "action", "anchor", "conditions", "effects", "evidence_ids"),
        )
        summary = str(raw_rule.get("summary", "")).strip()
        if not summary:
            raise ValueError(f"rule {index} must include a natural-language summary")
        evidence_ids = tuple(str(item) for item in raw_rule.get("evidence_ids", []))
        if not evidence_ids:
            raise ValueError(f"rule {index} must cite at least one evidence id")
        conditions = tuple(
            CellCondition.from_data(_offset_item(item))
            for item in raw_rule["conditions"]
        )
        effects = tuple(
            CellEffect.from_data(_offset_item(item)) for item in raw_rule["effects"]
        )
        rules.append(
            GeneralizedRule(
                id=str(raw_rule.get("id") or ""),
                action=_action_name(raw_rule["action"]),
                anchor=_anchor_value(raw_rule["anchor"]),
                conditions=conditions,
                effects=effects,
                evidence_ids=evidence_ids,
                summary=summary,
                result_state=(
                    str(raw_rule["result_state"])
                    if raw_rule.get("result_state") is not None
                    else None
                ),
                levels_completed=(
                    int(raw_rule["levels_completed"])
                    if raw_rule.get("levels_completed") is not None
                    else None
                ),
            )
        )
    return rules


def _require_fields(data: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field not in data:
            raise ValueError(f"missing required field '{field}'")


def _action_name(value: Any) -> str:
    name = str(value).strip().upper()
    if name not in GameAction.__members__:
        raise ValueError(f"unknown action '{value}'")
    return name


def _anchor_value(value: Any) -> int:
    if isinstance(value, dict):
        if "value" not in value:
            raise ValueError("anchor object must include field 'value'")
        value = value["value"]
    return int(value)


def _offset_item(data: dict[str, Any]) -> dict[str, Any]:
    if "offset" not in data:
        return data
    dx, dy = data["offset"]
    converted = {"dx": dx, "dy": dy}
    if "equals" in data:
        converted["value"] = data["equals"]
    if "set" in data:
        converted["value"] = data["set"]
    return converted


def _logical_condition(condition: CellCondition) -> dict[str, Any]:
    return {"offset": [condition.dx, condition.dy], "equals": condition.value}


def _logical_effect(effect: CellEffect) -> dict[str, Any]:
    return {"offset": [effect.dx, effect.dy], "set": effect.value}
