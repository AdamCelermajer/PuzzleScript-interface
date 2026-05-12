from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from client.engine.types import GameAction

from .model import SymbolFrame


DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "output" / "live_rules.md"
DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "output" / "live_rules.json"
DEFAULT_JOURNAL_PATH = Path(__file__).resolve().parent / "output" / "live_journal.md"
DEFAULT_COMPACT_OUTPUT_PATH = (
    Path(__file__).resolve().parent / "output" / "live_rules_compact.md"
)
STORE_VERSION = 5

ACTION_ACTOR_SYMBOL = "P"
EMPTY_SYMBOLS = {".", "O"}
TARGET_SYMBOLS = {"O", "@"}
CRATE_SYMBOLS = {"*", "@"}


def _action_name(action: GameAction | str) -> str:
    return action.name if isinstance(action, GameAction) else str(action)


def _attributed_action(action: str, actor_symbol: str) -> str:
    return f"{action}({actor_symbol})"


def _cell_object(symbol: str | None) -> str | None:
    if symbol == ACTION_ACTOR_SYMBOL:
        return ACTION_ACTOR_SYMBOL
    if symbol in CRATE_SYMBOLS:
        return "*"
    return None


def _is_clear_for_motion(symbol: str | None) -> bool:
    return symbol in EMPTY_SYMBOLS


def _is_known_target(symbol: str | None) -> bool:
    return symbol in TARGET_SYMBOLS


def _coord_fact(index: int, dx: int, dy: int) -> str:
    return f"{_axis_fact('x', dx * index)},{_axis_fact('y', dy * index)}"


def _axis_fact(axis: str, offset: int) -> str:
    if offset == 0:
        return axis
    if offset > 0:
        return f"{axis}+{offset}"
    return f"{axis}{offset}"


@dataclass(frozen=True)
class RelativeCondition:
    index: int
    kind: str
    symbol: str | None = None

    @classmethod
    def from_symbol(cls, index: int, symbol: str) -> "RelativeCondition":
        if symbol in EMPTY_SYMBOLS:
            return cls(index=index, kind="clear")
        if symbol in CRATE_SYMBOLS:
            return cls(index=index, kind="crate", symbol="*a")
        return cls(index=index, kind="at", symbol=symbol)

    def matches(self, frame: SymbolFrame, x: int, y: int, dx: int, dy: int) -> bool:
        symbol = frame.cell(x + dx * self.index, y + dy * self.index)
        if self.kind == "clear":
            return _is_clear_for_motion(symbol)
        if self.kind == "crate":
            return symbol in CRATE_SYMBOLS
        return symbol == self.symbol

    def facts(self, dx: int, dy: int, crate_variable: str) -> tuple[str, ...]:
        coord = _coord_fact(self.index, dx, dy)
        if self.kind == "clear":
            return (f"NOT At(#,{coord})", f"NOT At({crate_variable},{coord})")
        if self.kind == "crate":
            return (f"At(*a,{coord})",)
        return (f"At({self.symbol},{coord})",)

    def to_data(self) -> dict:
        return {
            "index": self.index,
            "kind": self.kind,
            "symbol": self.symbol,
        }

    @classmethod
    def from_data(cls, data: dict) -> "RelativeCondition":
        return cls(
            index=int(data["index"]),
            kind=str(data["kind"]),
            symbol=(str(data["symbol"]) if data.get("symbol") is not None else None),
        )


@dataclass(frozen=True)
class RelativeEffect:
    index: int
    kind: str
    symbol: str

    def fact(self, dx: int, dy: int) -> str:
        coord = _coord_fact(self.index, dx, dy)
        verb = "Remove" if self.kind == "clear" else "Add"
        symbol = "*a" if self.symbol == "*" else self.symbol
        return f"{verb}(At({symbol},{coord}))"

    def to_data(self) -> dict:
        return {"index": self.index, "kind": self.kind, "symbol": self.symbol}

    @classmethod
    def from_data(cls, data: dict) -> "RelativeEffect":
        return cls(
            index=int(data["index"]),
            kind=str(data["kind"]),
            symbol=str(data["symbol"]),
        )


@dataclass
class LiveRule:
    id: str
    action: str
    actor_symbol: str
    dx: int
    dy: int
    conditions: tuple[RelativeCondition, ...]
    effects: tuple[RelativeEffect, ...]
    status: str = "active"
    observations: int = 1
    prediction_hits: int = 0
    prediction_failures: list[str] = field(default_factory=list)
    parent_id: str | None = None
    sibling_group: str | None = None
    specificity: int = 0
    created_from_failure: str | None = None

    @property
    def attributed_action(self) -> str:
        return _attributed_action(self.action, self.actor_symbol)

    @property
    def anchor_symbol(self) -> str:
        return self.actor_symbol

    @property
    def condition_facts(self) -> tuple[str, ...]:
        return _condition_facts(self.conditions, self.dx, self.dy)

    @property
    def effect_facts(self) -> tuple[str, ...]:
        return tuple(effect.fact(self.dx, self.dy) for effect in self.effects)

    def predictions(
        self,
        frame: SymbolFrame,
        target_positions: set[tuple[int, int]],
    ) -> list[SymbolFrame]:
        predictions = []
        for x, y in frame.positions(self.actor_symbol):
            if not all(
                condition.matches(frame, x, y, self.dx, self.dy)
                for condition in self.conditions
            ):
                continue
            predicted = _apply_effects(
                frame, x, y, self.dx, self.dy, self.effects, target_positions
            )
            if predicted is not None:
                predictions.append(predicted)
        return predictions

    def __post_init__(self) -> None:
        if self.specificity == 0:
            self.specificity = len(self.conditions)


@dataclass
class LiveFailure:
    action: str
    expected_rule_ids: tuple[str, ...]
    observed_before: list[str]
    observed_after: list[str]


class LiveRuleModel:
    """Learns LIVE-style action effects over attributed PuzzleScript percepts."""

    def __init__(
        self,
        output_path: str | Path | None = None,
        store_path: str | Path | None = None,
        journal_path: str | Path | None = None,
        load_existing: bool = True,
        compact_output_path: str | Path | None = None,
    ) -> None:
        self.output_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH
        self.store_path = Path(store_path) if store_path else self._default_store_path()
        self.journal_path = (
            Path(journal_path) if journal_path else self._default_journal_path()
        )
        self.compact_output_path = (
            Path(compact_output_path)
            if compact_output_path
            else self._default_compact_output_path()
        )
        self.action_deltas: dict[tuple[str, str], tuple[int, int]] = {}
        self.context_attempts: dict[str, int] = {}
        self.target_positions: set[tuple[int, int]] = set()
        self.rules: list[LiveRule] = []
        self.failures: list[LiveFailure] = []
        self._next_id = 1
        self.loaded_rule_count = 0
        if load_existing:
            self._load()

    def seed_target_positions(self, positions: Iterable[tuple[int, int]]) -> None:
        self.target_positions.update((int(x), int(y)) for x, y in positions)

    def observe(
        self, before: SymbolFrame, action: GameAction | str, after: SymbolFrame
    ) -> None:
        action_name = _action_name(action)
        self._learn_static_percepts(before)
        self._learn_static_percepts(after)
        learned_deltas = self._learn_action_deltas(before, action_name, after)
        candidate_deltas = [
            (symbol, dx, dy)
            for (known_action, symbol), (dx, dy) in self.action_deltas.items()
            if known_action == action_name and symbol == ACTION_ACTOR_SYMBOL
        ]

        for actor_symbol, dx, dy in candidate_deltas:
            rule = self._percept_rule_from_transition(
                before, action_name, after, actor_symbol, dx, dy
            )
            if rule is None:
                continue
            existing = self._find_matching_rule(rule)
            if existing is not None:
                existing.observations += 1
                self._append_journal(
                    f"observed existing {existing.id}: "
                    f"action={existing.attributed_action}, "
                    f"observations={existing.observations}"
                )
            else:
                self.rules.append(rule)
                self._append_journal(
                    f"created {rule.id}: action={rule.attributed_action}, "
                    f"conditions={rule.condition_facts}, "
                    f"effects={rule.effect_facts or ('NoChange',)}"
                )

        if learned_deltas or candidate_deltas:
            self._save()
            self.write()

    def predict(self, before: SymbolFrame, action: GameAction | str) -> list[SymbolFrame]:
        self._learn_static_percepts(before)
        action_name = _action_name(action)
        predictions: list[SymbolFrame] = []
        seen: set[SymbolFrame] = set()
        for _rule, predicted in self._preferred_prediction_candidates(
            before, action_name
        ):
            if predicted not in seen:
                predictions.append(predicted)
                seen.add(predicted)
        return predictions

    def record_prediction_result(
        self,
        before: SymbolFrame,
        action: GameAction | str,
        after: SymbolFrame,
        predictions: list[SymbolFrame],
    ) -> None:
        if not predictions:
            return

        self._learn_static_percepts(before)
        self._learn_static_percepts(after)
        action_name = _action_name(action)
        matching = [
            rule
            for rule, predicted in self._preferred_prediction_candidates(
                before, action_name
            )
            if predicted == after
        ]
        if matching:
            for rule in matching:
                rule.prediction_hits += 1
            self._save()
            self._append_journal(
                f"prediction hit: action={action_name}, "
                f"rules={tuple(rule.id for rule in matching)}"
            )
            self.write()
            return

        expected_rules = self._rules_that_predicted(before, action_name, predictions)
        expected_ids = tuple(rule.id for rule in expected_rules)
        failure = LiveFailure(
            action=action_name,
            expected_rule_ids=expected_ids,
            observed_before=before.to_rows(),
            observed_after=after.to_rows(),
        )
        self.failures.append(failure)
        failure_label = f"F{len(self.failures):03d}"
        for rule in expected_rules:
            rule.prediction_failures.append(
                f"{failure_label}: observed {before.to_rows()} -> {after.to_rows()}"
            )
            self._create_sibling_family(rule, before, after, failure_label)
        self._save()
        self._append_journal(
            f"prediction failure: action={action_name}, rules={expected_ids}"
        )
        self.write()

    def active_rules(self, action: str | None = None) -> list[LiveRule]:
        return [
            rule
            for rule in self.rules
            if rule.status == "active" and (action is None or rule.action == action)
        ]

    def action_has_delta(self, action: GameAction) -> bool:
        action_name = _action_name(action)
        return any(
            known_action == action_name for known_action, _symbol in self.action_deltas
        )

    def unseen_context_action(
        self, frame: SymbolFrame, actions: list[GameAction]
    ) -> tuple[GameAction, tuple[str, str, int, int, tuple[str, ...]]] | None:
        self._learn_static_percepts(frame)
        for action in actions:
            action_name = _action_name(action)
            for (known_action, actor_symbol), (dx, dy) in sorted(
                self.action_deltas.items()
            ):
                if known_action != action_name:
                    continue
                for x, y in frame.positions(actor_symbol):
                    for length in (3, 2):
                        line = frame.line(x, y, dx, dy, length)
                        if line is None:
                            continue
                        conditions = self._conditions_from_line(line)
                        context = (
                            actor_symbol,
                            _attributed_action(action_name, actor_symbol),
                            dx,
                            dy,
                            _condition_facts(conditions, dx, dy),
                        )
                        if self._context_observations(context) == 0:
                            return action, context
        return None

    def record_explorer_selection(
        self,
        action: GameAction,
        reason: str,
        context: tuple | None = None,
    ) -> None:
        if context is not None and reason == "current_unseen_context":
            key = self._context_key(context)
            self.context_attempts[key] = self.context_attempts.get(key, 0) + 1
            self._save()
        suffix = f", context={context}" if context is not None else ""
        self._append_journal(f"selected {action.name}: {reason}{suffix}")

    def write(self, final: bool = False, extra_sections: list[str] | None = None) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            self._render(final=final, extra_sections=extra_sections or []),
            encoding="utf-8",
        )
        self.compact_output_path.parent.mkdir(parents=True, exist_ok=True)
        self.compact_output_path.write_text(
            self._render_compact_rules(),
            encoding="utf-8",
        )

    def _preferred_prediction_candidates(
        self, before: SymbolFrame, action_name: str
    ) -> list[tuple[LiveRule, SymbolFrame]]:
        candidates = self._prediction_candidates(before, action_name)
        by_family: dict[str, list[tuple[LiveRule, SymbolFrame]]] = {}
        for rule, predicted in candidates:
            by_family.setdefault(self._rule_family(rule), []).append((rule, predicted))

        preferred: list[tuple[LiveRule, SymbolFrame]] = []
        for family_candidates in by_family.values():
            best_specificity = max(
                rule.specificity for rule, _predicted in family_candidates
            )
            preferred.extend(
                (rule, predicted)
                for rule, predicted in family_candidates
                if rule.specificity == best_specificity
            )
        return preferred

    def _prediction_candidates(
        self, before: SymbolFrame, action_name: str
    ) -> list[tuple[LiveRule, SymbolFrame]]:
        candidates: list[tuple[LiveRule, SymbolFrame]] = []
        for rule in self.active_rules(action_name):
            for predicted in rule.predictions(before, self.target_positions):
                candidates.append((rule, predicted))
        return candidates

    def _rule_family(self, rule: LiveRule) -> str:
        return rule.sibling_group or rule.id

    def _rules_that_predicted(
        self,
        before: SymbolFrame,
        action_name: str,
        predictions: list[SymbolFrame],
    ) -> list[LiveRule]:
        predicted_set = set(predictions)
        rules: list[LiveRule] = []
        seen_ids: set[str] = set()
        for rule, predicted in self._preferred_prediction_candidates(before, action_name):
            if predicted not in predicted_set or rule.id in seen_ids:
                continue
            rules.append(rule)
            seen_ids.add(rule.id)
        return rules

    def _create_sibling_family(
        self,
        parent: LiveRule,
        failed_before: SymbolFrame,
        observed_after: SymbolFrame,
        failure_label: str,
    ) -> None:
        group = parent.sibling_group or f"G{parent.id}"
        parent.status = "split"
        parent.sibling_group = group

        success = LiveRule(
            id=self._new_rule_id(),
            action=parent.action,
            actor_symbol=parent.actor_symbol,
            dx=parent.dx,
            dy=parent.dy,
            conditions=parent.conditions,
            effects=parent.effects,
            observations=parent.observations,
            prediction_hits=parent.prediction_hits,
            parent_id=parent.id,
            sibling_group=group,
            specificity=len(parent.conditions),
            created_from_failure=f"{failure_label}: preserves prior success",
        )
        failure = self._failure_sibling_from_transition(
            parent, failed_before, observed_after, group, failure_label
        )

        created = []
        for rule in (success, failure):
            if rule is None:
                continue
            if self._find_active_matching_rule(rule) is not None:
                continue
            self.rules.append(rule)
            created.append(rule.id)

        self._append_journal(
            f"created sibling family {group} from {parent.id}: "
            f"siblings={tuple(created)}"
        )

    def _failure_sibling_from_transition(
        self,
        parent: LiveRule,
        before: SymbolFrame,
        after: SymbolFrame,
        group: str,
        failure_label: str,
    ) -> LiveRule | None:
        for x, y in before.positions(parent.actor_symbol):
            if not all(
                condition.matches(before, x, y, parent.dx, parent.dy)
                for condition in parent.conditions
            ):
                continue
            length = min(3, len(parent.conditions) + 1)
            before_line = before.line(x, y, parent.dx, parent.dy, length)
            after_line = after.line(x, y, parent.dx, parent.dy, length)
            if before_line is None or after_line is None:
                continue
            return LiveRule(
                id=self._new_rule_id(),
                action=parent.action,
                actor_symbol=parent.actor_symbol,
                dx=parent.dx,
                dy=parent.dy,
                conditions=self._conditions_from_line(before_line),
                effects=self._effects_from_lines(before_line, after_line),
                parent_id=parent.id,
                sibling_group=group,
                specificity=length,
                created_from_failure=f"{failure_label}: observed counterexample",
            )
        return None

    def _learn_action_deltas(
        self, before: SymbolFrame, action: str, after: SymbolFrame
    ) -> list[tuple[str, int, int]]:
        learned = []
        before_positions = set(before.positions(ACTION_ACTOR_SYMBOL))
        after_positions = set(after.positions(ACTION_ACTOR_SYMBOL))
        if not before_positions or not after_positions:
            return learned

        vanished = before_positions - after_positions
        emerged = after_positions - before_positions
        for old_x, old_y in vanished:
            for new_x, new_y in emerged:
                dx = new_x - old_x
                dy = new_y - old_y
                if abs(dx) + abs(dy) != 1:
                    continue
                key = (action, ACTION_ACTOR_SYMBOL)
                if key not in self.action_deltas:
                    self.action_deltas[key] = (dx, dy)
                    learned.append((ACTION_ACTOR_SYMBOL, dx, dy))
                    self._append_journal(
                        f"observed action direction {_attributed_action(action, ACTION_ACTOR_SYMBOL)}: "
                        f"dx={dx}, dy={dy}"
                    )
        return learned

    def _learn_static_percepts(self, frame: SymbolFrame) -> None:
        for y, row in enumerate(frame.grid):
            for x, symbol in enumerate(row):
                if _is_known_target(symbol):
                    self.target_positions.add((x, y))

    def _percept_rule_from_transition(
        self,
        before: SymbolFrame,
        action: str,
        after: SymbolFrame,
        actor_symbol: str,
        dx: int,
        dy: int,
    ) -> LiveRule | None:
        if actor_symbol != ACTION_ACTOR_SYMBOL:
            return None

        changed = set(before.changed_positions(after))
        for x, y in before.positions(actor_symbol):
            if changed:
                line_indexes = self._changed_line_indexes(changed, x, y, dx, dy)
                if line_indexes is None:
                    continue
                length = max(2, min(3, max(line_indexes) + 1))
            else:
                length = self._unchanged_line_length(before, x, y, dx, dy)

            before_line = before.line(x, y, dx, dy, length)
            after_line = after.line(x, y, dx, dy, length)
            if before_line is None or after_line is None:
                continue
            if before_line == after_line and changed:
                continue
            return LiveRule(
                id=self._new_rule_id(),
                action=action,
                actor_symbol=actor_symbol,
                dx=dx,
                dy=dy,
                conditions=self._conditions_from_line(before_line),
                effects=self._effects_from_lines(before_line, after_line),
                specificity=length,
            )
        return None

    def _conditions_from_line(
        self, line: Iterable[str]
    ) -> tuple[RelativeCondition, ...]:
        return tuple(
            RelativeCondition.from_symbol(index, symbol)
            for index, symbol in enumerate(line)
        )

    def _effects_from_lines(
        self,
        before_line: tuple[str, ...],
        after_line: tuple[str, ...],
    ) -> tuple[RelativeEffect, ...]:
        effects: list[RelativeEffect] = []
        for object_symbol in (ACTION_ACTOR_SYMBOL, "*"):
            before_index = _object_index(before_line, object_symbol)
            after_index = _object_index(after_line, object_symbol)
            if before_index == after_index:
                continue
            if before_index is not None:
                effects.append(
                    RelativeEffect(
                        index=before_index, kind="clear", symbol=object_symbol
                    )
                )
            if after_index is not None:
                effects.append(
                    RelativeEffect(index=after_index, kind="set", symbol=object_symbol)
                )
        return tuple(effects)

    def _unchanged_line_length(
        self,
        frame: SymbolFrame,
        x: int,
        y: int,
        dx: int,
        dy: int,
    ) -> int:
        front = frame.cell(x + dx, y + dy)
        if front in CRATE_SYMBOLS:
            three = frame.line(x, y, dx, dy, 3)
            if three is not None:
                return 3
        return 2

    def _changed_line_indexes(
        self,
        changed: set[tuple[int, int]],
        x: int,
        y: int,
        dx: int,
        dy: int,
    ) -> list[int] | None:
        indexes = []
        for cx, cy in changed:
            if dx == 0:
                if cx != x:
                    return None
                offset = cy - y
                if dy == 0 or offset % dy != 0:
                    return None
                index = offset // dy
            else:
                if cy != y:
                    return None
                offset = cx - x
                if offset % dx != 0:
                    return None
                index = offset // dx
            if index < 0 or index > 2:
                return None
            indexes.append(index)
        return indexes

    def _find_matching_rule(self, candidate: LiveRule) -> LiveRule | None:
        return self._find_active_matching_rule(candidate)

    def _find_active_matching_rule(self, candidate: LiveRule) -> LiveRule | None:
        for rule in self.rules:
            if (
                rule.status == "active"
                and rule.action == candidate.action
                and rule.actor_symbol == candidate.actor_symbol
                and rule.dx == candidate.dx
                and rule.dy == candidate.dy
                and rule.conditions == candidate.conditions
                and rule.effects == candidate.effects
            ):
                return rule
        return None

    def _context_observations(self, context: tuple) -> int:
        actor_symbol, attributed_action, dx, dy, condition_facts = context
        attempts = self.context_attempts.get(self._context_key(context), 0)
        rule_observations = 0
        for rule in self.active_rules():
            if (
                rule.actor_symbol != actor_symbol
                or rule.attributed_action != attributed_action
                or rule.dx != dx
                or rule.dy != dy
            ):
                continue
            if _facts_are_prefix(rule.condition_facts, tuple(condition_facts)):
                rule_observations += rule.observations
        return attempts + rule_observations

    def _context_key(self, context: tuple) -> str:
        return repr(context)

    def _new_rule_id(self) -> str:
        rule_id = f"R{self._next_id:03d}"
        self._next_id += 1
        return rule_id

    def _default_store_path(self) -> Path:
        if self.output_path == DEFAULT_OUTPUT_PATH:
            return DEFAULT_STORE_PATH
        return self.output_path.with_suffix(".json")

    def _default_journal_path(self) -> Path:
        if self.output_path == DEFAULT_OUTPUT_PATH:
            return DEFAULT_JOURNAL_PATH
        return self.output_path.with_name(f"{self.output_path.stem}_journal.md")

    def _default_compact_output_path(self) -> Path:
        if self.output_path == DEFAULT_OUTPUT_PATH:
            return DEFAULT_COMPACT_OUTPUT_PATH
        return self.output_path.with_name(f"{self.output_path.stem}_compact.md")

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.action_deltas = {
            (str(item["action"]), str(item["symbol"])): (
                int(item["dx"]),
                int(item["dy"]),
            )
            for item in data.get("action_deltas", [])
            if str(item.get("symbol")) == ACTION_ACTOR_SYMBOL
        }

        if int(data.get("version", 0)) != STORE_VERSION:
            self.loaded_rule_count = 0
            self._append_journal(
                f"skipped old symbol-line rules from {self.store_path}; "
                f"loaded {len(self.action_deltas)} action deltas"
            )
            return

        self.context_attempts = {
            str(item["context"]): int(item.get("attempts", 0))
            for item in data.get("context_attempts", [])
        }
        self.target_positions = {
            (int(item["x"]), int(item["y"]))
            for item in data.get("target_positions", [])
        }
        self.rules = [
            LiveRule(
                id=str(item["id"]),
                action=str(item["action"]),
                actor_symbol=str(item["actor_symbol"]),
                dx=int(item["dx"]),
                dy=int(item["dy"]),
                conditions=tuple(
                    RelativeCondition.from_data(condition)
                    for condition in item.get("conditions", [])
                ),
                effects=tuple(
                    RelativeEffect.from_data(effect)
                    for effect in item.get("effects", [])
                ),
                status=str(item.get("status", "active")),
                observations=int(item.get("observations", 1)),
                prediction_hits=int(item.get("prediction_hits", 0)),
                prediction_failures=[
                    str(failure) for failure in item.get("prediction_failures", [])
                ],
                parent_id=(
                    str(item["parent_id"]) if item.get("parent_id") is not None else None
                ),
                sibling_group=(
                    str(item["sibling_group"])
                    if item.get("sibling_group") is not None
                    else None
                ),
                specificity=int(item.get("specificity", 0)),
                created_from_failure=(
                    str(item["created_from_failure"])
                    if item.get("created_from_failure") is not None
                    else None
                ),
            )
            for item in data.get("rules", [])
            if str(item.get("actor_symbol")) == ACTION_ACTOR_SYMBOL
        ]
        self.failures = [
            LiveFailure(
                action=str(item["action"]),
                expected_rule_ids=tuple(
                    str(rule_id) for rule_id in item.get("expected_rule_ids", [])
                ),
                observed_before=[str(row) for row in item.get("observed_before", [])],
                observed_after=[str(row) for row in item.get("observed_after", [])],
            )
            for item in data.get("failures", [])
        ]
        self._next_id = int(data.get("next_id", self._next_id))
        self.loaded_rule_count = len(self.rules)
        self._append_journal(
            f"loaded {self.loaded_rule_count} persisted percept rules from {self.store_path}"
        )

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._to_data(), indent=2),
            encoding="utf-8",
        )

    def _to_data(self) -> dict:
        return {
            "version": STORE_VERSION,
            "next_id": self._next_id,
            "context_attempts": [
                {"context": context, "attempts": attempts}
                for context, attempts in sorted(self.context_attempts.items())
            ],
            "target_positions": [
                {"x": x, "y": y} for x, y in sorted(self.target_positions)
            ],
            "action_deltas": [
                {
                    "action": action,
                    "symbol": symbol,
                    "dx": dx,
                    "dy": dy,
                }
                for (action, symbol), (dx, dy) in sorted(self.action_deltas.items())
            ],
            "rules": [
                {
                    "id": rule.id,
                    "action": rule.action,
                    "attributed_action": rule.attributed_action,
                    "actor_symbol": rule.actor_symbol,
                    "dx": rule.dx,
                    "dy": rule.dy,
                    "conditions": [
                        condition.to_data() for condition in rule.conditions
                    ],
                    "effects": [effect.to_data() for effect in rule.effects],
                    "status": rule.status,
                    "observations": rule.observations,
                    "prediction_hits": rule.prediction_hits,
                    "prediction_failures": list(rule.prediction_failures),
                    "parent_id": rule.parent_id,
                    "sibling_group": rule.sibling_group,
                    "specificity": rule.specificity,
                    "created_from_failure": rule.created_from_failure,
                }
                for rule in self.rules
            ],
            "failures": [
                {
                    "action": failure.action,
                    "expected_rule_ids": list(failure.expected_rule_ids),
                    "observed_before": failure.observed_before,
                    "observed_after": failure.observed_after,
                }
                for failure in self.failures
            ],
        }

    def _append_journal(self, event: str) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.journal_path.exists():
            self.journal_path.write_text(
                "# LIVE Sokoban Rule Growth Journal\n\n",
                encoding="utf-8",
            )
        timestamp = datetime.now().isoformat(timespec="seconds")
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(f"- {timestamp} - {event}\n")

    def _render(self, final: bool, extra_sections: list[str]) -> str:
        lines = [
            "# LIVE Sokoban",
            "",
            "State is represented as PuzzleScript symbol percepts and coordinate facts.",
            "Actions are attributed to the observed actor, for example `ACTION2(P)`.",
            "Prediction failures create complementary sibling rules.",
            f"Persistent rule store: `{self.store_path}`.",
            f"Append-only growth journal: `{self.journal_path}`.",
            f"Loaded persisted percept rules at start: {self.loaded_rule_count}.",
            "",
            "## Observed Action Directions",
            "",
        ]
        if not self.action_deltas:
            lines.append("- None yet.")
        for (action, symbol), (dx, dy) in sorted(self.action_deltas.items()):
            lines.append(f"- {_attributed_action(action, symbol)}: dx={dx}, dy={dy}")

        lines.extend(["", "## Known `O/@` Cells", ""])
        if not self.target_positions:
            lines.append("- None yet.")
        for x, y in sorted(self.target_positions):
            lines.append(f"- At(O-or-@,{x},{y})")

        lines.extend(["", "## Tested Interaction Contexts", ""])
        if not self.context_attempts:
            lines.append("- None yet.")
        for context, attempts in sorted(self.context_attempts.items()):
            lines.append(f"- {context}: {attempts}")

        lines.extend(["", "## Active Percept Rules", ""])
        active = self.active_rules()
        if not active:
            lines.append("- None yet.")
        for rule in active:
            lines.extend(_render_rule_block(rule))

        lines.extend(["## Sibling Rule Families", ""])
        sibling_rules = [rule for rule in self.rules if rule.sibling_group]
        if not sibling_rules:
            lines.append("- None yet.")
        for group in sorted(
            {rule.sibling_group for rule in sibling_rules if rule.sibling_group}
        ):
            lines.append(f"### {group}")
            for rule in [item for item in sibling_rules if item.sibling_group == group]:
                lines.append(
                    f"- {rule.id} [{rule.status}] parent={rule.parent_id or '-'} "
                    f"specificity={rule.specificity} "
                    f"{_join_logic(rule.condition_facts)} -> "
                    f"{_prediction_statement(rule.effect_facts)}"
                )
                if rule.created_from_failure:
                    lines.append(f"  created_from_failure: {rule.created_from_failure}")
            lines.append("")

        lines.extend(["## Prediction Failures", ""])
        if not self.failures:
            lines.append("- None recorded.")
        for index, failure in enumerate(self.failures, start=1):
            lines.append(
                f"- F{index:03d}: action={failure.action}, "
                f"rules={failure.expected_rule_ids}"
            )

        if extra_sections:
            lines.extend(["", *extra_sections])

        if final:
            lines.extend(["", "## Final Rule Set", ""])
            for rule in active:
                lines.extend(_render_rule_block(rule))

        return "\n".join(lines) + "\n"

    def _render_compact_rules(self) -> str:
        lines = []
        seen = set()
        for rule in self.active_rules():
            line = _compact_rule_line(rule)
            if line in seen:
                continue
            lines.append(line)
            seen.add(line)
        if not lines:
            return ""
        return "\n".join(lines) + "\n"


def _facts_are_prefix(shorter: tuple[str, ...], longer: tuple[str, ...]) -> bool:
    if len(shorter) > len(longer):
        return False
    return longer[: len(shorter)] == shorter


def _condition_facts(
    conditions: tuple[RelativeCondition, ...], dx: int, dy: int
) -> tuple[str, ...]:
    facts: list[str] = []
    crate_seen = False
    for condition in conditions:
        if condition.kind == "clear":
            crate_variable = "*b" if crate_seen else "*a"
        else:
            crate_variable = "*a"
        facts.extend(condition.facts(dx, dy, crate_variable))
        if condition.kind == "crate":
            crate_seen = True
    return tuple(facts)


def _object_index(line: tuple[str, ...], object_symbol: str) -> int | None:
    for index, symbol in enumerate(line):
        if _cell_object(symbol) == object_symbol:
            return index
    return None


def _render_rule_block(rule: LiveRule) -> list[str]:
    return [
        f"### {rule.id}",
        "",
        "```text",
        f"Index:      {rule.id}",
        f"Condition:  {_join_logic(rule.condition_facts)}",
        f"Action:     {rule.attributed_action}",
        f"Prediction: {_prediction_statement(rule.effect_facts)}",
        f"Sibling:    {rule.sibling_group or rule.parent_id or '-'}",
        "```",
        "",
    ]


def _compact_rule_line(rule: LiveRule) -> str:
    return (
        f"{rule.attributed_action}: "
        f"{_compact_logic(rule.condition_facts)} => "
        f"{_compact_prediction(rule.effect_facts)}"
    )


def _compact_logic(facts: tuple[str, ...]) -> str:
    if not facts:
        return "TRUE"
    return " & ".join(_compact_fact(fact) for fact in facts)


def _compact_prediction(effect_facts: tuple[str, ...]) -> str:
    if not effect_facts:
        return "NoChange"
    return " & ".join(_compact_fact(fact) for fact in effect_facts)


def _compact_fact(fact: str) -> str:
    if fact.startswith("NOT "):
        return f"!{fact[len('NOT '):]}"
    if fact.startswith("Remove(") and fact.endswith(")"):
        return f"!{fact[len('Remove('):-1]}"
    if fact.startswith("Add(") and fact.endswith(")"):
        return fact[len("Add(") : -1]
    return fact


def _join_logic(facts: tuple[str, ...]) -> str:
    if not facts:
        return "TRUE"
    return " AND ".join(facts)


def _prediction_statement(effect_facts: tuple[str, ...]) -> str:
    if not effect_facts:
        return "NoChange"
    statements = []
    for fact in effect_facts:
        if fact.startswith("Remove(At(") and fact.endswith("))"):
            inner = fact[len("Remove(") : -1]
            statements.append(f"NOT {inner}")
        elif fact.startswith("Add(At(") and fact.endswith("))"):
            statements.append(fact[len("Add(") : -1])
        else:
            statements.append(fact)
    return " AND ".join(statements)


def _apply_effects(
    frame: SymbolFrame,
    x: int,
    y: int,
    dx: int,
    dy: int,
    effects: tuple[RelativeEffect, ...],
    target_positions: set[tuple[int, int]],
) -> SymbolFrame | None:
    if not effects:
        return frame

    rows = [list(row) for row in frame.grid]
    object_by_position: dict[tuple[int, int], str | None] = {}
    for effect in effects:
        cx = x + dx * effect.index
        cy = y + dy * effect.index
        if cy < 0 or cy >= len(rows) or cx < 0 or cx >= len(rows[cy]):
            return None
        object_by_position.setdefault((cx, cy), _cell_object(frame.cell(cx, cy)))

    for effect in effects:
        position = (x + dx * effect.index, y + dy * effect.index)
        if effect.kind == "clear":
            if object_by_position.get(position) == effect.symbol:
                object_by_position[position] = None
        elif effect.kind == "set":
            object_by_position[position] = effect.symbol

    for (cx, cy), object_symbol in object_by_position.items():
        original = frame.cell(cx, cy)
        if original is None:
            return None
        rows[cy][cx] = _render_cell(
            original=original,
            object_symbol=object_symbol,
            is_target=(cx, cy) in target_positions or _is_known_target(original),
        )

    return SymbolFrame(tuple(tuple(row) for row in rows))


def _render_cell(original: str, object_symbol: str | None, is_target: bool) -> str:
    if original == "#":
        return "#"
    if object_symbol == ACTION_ACTOR_SYMBOL:
        return ACTION_ACTOR_SYMBOL
    if object_symbol == "*":
        return "@" if is_target else "*"
    return "O" if is_target else "."
