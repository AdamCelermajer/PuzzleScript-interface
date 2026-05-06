from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from client.engine.types import GameAction

from .model import CellChange, RawFrame


DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent / "output" / "strict_parameterless_live_rules.md"
)
DEFAULT_STORE_PATH = (
    Path(__file__).resolve().parent / "output" / "strict_parameterless_live_rules.json"
)
DEFAULT_JOURNAL_PATH = (
    Path(__file__).resolve().parent / "output" / "strict_parameterless_live_journal.md"
)


def _action_name(action: GameAction | str) -> str:
    return action.name if isinstance(action, GameAction) else str(action)


@dataclass
class StrictRule:
    id: str
    action: str
    before: RawFrame
    after: RawFrame
    changed_cells: tuple[CellChange, ...]
    status: str = "active"
    observations: int = 1
    prediction_hits: int = 0
    prediction_failures: list[str] = field(default_factory=list)

    def predicts(self, frame: RawFrame) -> RawFrame | None:
        if frame == self.before:
            return self.after
        return frame.apply_changes(self.changed_cells)


@dataclass
class RawLineRule:
    id: str
    action: str
    anchor_value: int
    dx: int
    dy: int
    before_values: tuple[int, ...]
    after_values: tuple[int, ...]
    status: str = "active"
    observations: int = 1
    prediction_hits: int = 0
    prediction_failures: list[str] = field(default_factory=list)

    def predictions(self, frame: RawFrame) -> list[RawFrame]:
        predictions = []
        for x, y in frame.positions(self.anchor_value):
            before_line = frame.line(x, y, self.dx, self.dy, len(self.before_values))
            if before_line != self.before_values:
                continue
            predicted = frame.apply_line(x, y, self.dx, self.dy, self.after_values)
            if predicted is not None:
                predictions.append(predicted)
        return predictions


@dataclass
class PredictionFailure:
    action: str
    expected_rule_ids: tuple[str, ...]
    observed_changes: tuple[CellChange, ...]


class StrictRuleModel:
    """Parameterless transition memory over raw integer frames."""

    def __init__(
        self,
        output_path: str | Path | None = None,
        store_path: str | Path | None = None,
        journal_path: str | Path | None = None,
        load_existing: bool = True,
    ) -> None:
        self.output_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH
        self.store_path = Path(store_path) if store_path else self._default_store_path()
        self.journal_path = (
            Path(journal_path) if journal_path else self._default_journal_path()
        )
        self.action_deltas: dict[tuple[str, int], tuple[int, int]] = {}
        self.context_attempts: dict[str, int] = {}
        self.rules: list[StrictRule] = []
        self.line_rules: list[RawLineRule] = []
        self.failures: list[PredictionFailure] = []
        self._next_id = 1
        self._next_line_id = 1
        self.loaded_rule_count = 0
        if load_existing:
            self._load()

    def observe(
        self, before: RawFrame, action: GameAction | str, after: RawFrame
    ) -> StrictRule:
        action_name = _action_name(action)
        learned_deltas = self._learn_action_deltas(before, action_name, after)
        changed_line_rules = self._learn_line_rules(before, action_name, after)
        existing = self._find_exact_rule(before, action_name, after)
        if existing is not None:
            existing.observations += 1
            self._save()
            self._append_journal(
                f"observed existing {existing.id}: action={action_name}, "
                f"observations={existing.observations}"
            )
            self.write()
            return existing

        rule = StrictRule(
            id=self._new_rule_id(),
            action=action_name,
            before=before,
            after=after,
            changed_cells=before.changed_cells(after),
        )
        self.rules.append(rule)
        self._save()
        self._append_journal(
            f"created {rule.id}: action={action_name}, "
            f"changed_cells={rule.changed_cells}"
        )
        if learned_deltas or changed_line_rules:
            self._append_journal(
                f"model expanded: deltas={len(learned_deltas)}, "
                f"line_rules={len(changed_line_rules)}"
            )
        self.write()
        return rule

    def predict(self, before: RawFrame, action: GameAction | str) -> list[RawFrame]:
        action_name = _action_name(action)
        predictions: list[RawFrame] = []
        seen: set[RawFrame] = set()
        for rule in self.active_rules(action_name):
            predicted = rule.predicts(before)
            if predicted is not None and predicted not in seen:
                predictions.append(predicted)
                seen.add(predicted)
        for rule in self.active_line_rules(action_name):
            for predicted in rule.predictions(before):
                if predicted not in seen:
                    predictions.append(predicted)
                    seen.add(predicted)
        return predictions

    def record_prediction_result(
        self,
        before: RawFrame,
        action: GameAction | str,
        after: RawFrame,
        predictions: list[RawFrame],
    ) -> None:
        if not predictions:
            return

        matching_rules = [
            rule
            for rule in self.active_rules(_action_name(action))
            if rule.predicts(before) == after
        ]
        matching_line_rules = [
            rule
            for rule in self.active_line_rules(_action_name(action))
            if after in rule.predictions(before)
        ]
        if matching_rules or matching_line_rules:
            for rule in matching_rules:
                rule.prediction_hits += 1
            for rule in matching_line_rules:
                rule.prediction_hits += 1
            self._save()
            self._append_journal(
                "prediction hit: action="
                f"{_action_name(action)}, rules="
                f"{tuple(rule.id for rule in [*matching_rules, *matching_line_rules])}"
            )
            self.write()
            return

        expected_ids = tuple(
            rule.id
            for rule in self.active_rules(_action_name(action))
            if rule.predicts(before) in predictions
        ) + tuple(
            rule.id
            for rule in self.active_line_rules(_action_name(action))
            if any(predicted in predictions for predicted in rule.predictions(before))
        )
        failure = PredictionFailure(
            action=_action_name(action),
            expected_rule_ids=expected_ids,
            observed_changes=before.changed_cells(after),
        )
        self.failures.append(failure)
        for rule in self.rules:
            if rule.id in expected_ids:
                rule.prediction_failures.append(
                    f"expected one learned result; observed {failure.observed_changes}"
                )
        for rule in self.line_rules:
            if rule.id in expected_ids:
                rule.prediction_failures.append(
                    f"expected one learned result; observed {failure.observed_changes}"
                )
        self._save()
        self._append_journal(
            f"prediction failure: action={failure.action}, rules={expected_ids}, "
            f"observed_changes={failure.observed_changes}"
        )
        self.write()

    def known_transition(self, before: RawFrame, action: GameAction | str) -> RawFrame | None:
        predictions = self.predict(before, action)
        return predictions[0] if predictions else None

    def active_rules(self, action: str | None = None) -> list[StrictRule]:
        return [
            rule
            for rule in self.rules
            if rule.status == "active" and (action is None or rule.action == action)
        ]

    def active_line_rules(self, action: str | None = None) -> list[RawLineRule]:
        return [
            rule
            for rule in self.line_rules
            if rule.status == "active" and (action is None or rule.action == action)
        ]

    def action_has_delta(self, action: GameAction) -> bool:
        action_name = _action_name(action)
        return any(known_action == action_name for known_action, _value in self.action_deltas)

    def unseen_context_action(
        self, frame: RawFrame, actions: list[GameAction]
    ) -> tuple[GameAction, tuple[int, str, int, int, tuple[int, ...]]] | None:
        for action in actions:
            action_name = _action_name(action)
            for (known_action, value), (dx, dy) in sorted(self.action_deltas.items()):
                if known_action != action_name:
                    continue
                for x, y in frame.positions(value):
                    for length in (3, 2):
                        before_values = frame.line(x, y, dx, dy, length)
                        if before_values is None:
                            continue
                        context = (value, action_name, dx, dy, before_values)
                        if self._context_observations(context) == 0:
                            return action, context
        return None

    def record_explorer_selection(
        self,
        action: GameAction,
        reason: str,
        context: tuple | None = None,
    ) -> None:
        if context is not None:
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

    def _find_exact_rule(
        self, before: RawFrame, action: str, after: RawFrame
    ) -> StrictRule | None:
        for rule in self.rules:
            if rule.before == before and rule.action == action and rule.after == after:
                return rule
        return None

    def _new_rule_id(self) -> str:
        rule_id = f"R{self._next_id:03d}"
        self._next_id += 1
        return rule_id

    def _new_line_rule_id(self) -> str:
        rule_id = f"L{self._next_line_id:03d}"
        self._next_line_id += 1
        return rule_id

    def _learn_action_deltas(
        self, before: RawFrame, action: str, after: RawFrame
    ) -> list[tuple[int, int, int]]:
        learned = []
        values = {
            value for row in before.grid for value in row if value != 0
        } | {value for row in after.grid for value in row if value != 0}

        for value in sorted(values):
            before_positions = set(before.positions(value))
            after_positions = set(after.positions(value))
            vanished = before_positions - after_positions
            emerged = after_positions - before_positions
            for old_x, old_y in vanished:
                for new_x, new_y in emerged:
                    dx = new_x - old_x
                    dy = new_y - old_y
                    if abs(dx) + abs(dy) != 1:
                        continue
                    key = (action, value)
                    if key not in self.action_deltas:
                        self.action_deltas[key] = (dx, dy)
                        learned.append((value, dx, dy))
                        self._append_journal(
                            f"created ActionDelta({action},{value},{dx},{dy})"
                        )
        return learned

    def _learn_line_rules(
        self, before: RawFrame, action: str, after: RawFrame
    ) -> list[RawLineRule]:
        learned = []
        for (known_action, value), (dx, dy) in sorted(self.action_deltas.items()):
            if known_action != action:
                continue
            rule = self._line_rule_from_transition(before, action, after, value, dx, dy)
            if rule is None:
                continue
            existing = self._find_matching_line_rule(rule)
            if existing is not None:
                existing.observations += 1
                self._append_journal(
                    f"observed existing {existing.id}: action={action}, "
                    f"observations={existing.observations}"
                )
                continue
            self.line_rules.append(rule)
            learned.append(rule)
            self._append_journal(
                f"created {rule.id}: action={action}, "
                f"line={rule.before_values}->{rule.after_values}, "
                f"delta=({rule.dx},{rule.dy})"
            )
        return learned

    def _line_rule_from_transition(
        self,
        before: RawFrame,
        action: str,
        after: RawFrame,
        anchor_value: int,
        dx: int,
        dy: int,
    ) -> RawLineRule | None:
        changed = set(before.changed_positions(after))
        for x, y in before.positions(anchor_value):
            if changed:
                line_indexes = self._changed_line_indexes(changed, x, y, dx, dy)
                if line_indexes is None:
                    continue
                length = max(2, min(3, max(line_indexes) + 1))
            else:
                length = 2

            before_values = before.line(x, y, dx, dy, length)
            after_values = after.line(x, y, dx, dy, length)
            if before_values is None or after_values is None:
                continue
            if before_values == after_values and changed:
                continue
            return RawLineRule(
                id=self._new_line_rule_id(),
                action=action,
                anchor_value=anchor_value,
                dx=dx,
                dy=dy,
                before_values=before_values,
                after_values=after_values,
            )
        return None

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

    def _find_matching_line_rule(self, candidate: RawLineRule) -> RawLineRule | None:
        for rule in self.line_rules:
            if (
                rule.action == candidate.action
                and rule.anchor_value == candidate.anchor_value
                and rule.dx == candidate.dx
                and rule.dy == candidate.dy
                and rule.before_values == candidate.before_values
                and rule.after_values == candidate.after_values
            ):
                return rule
        return None

    def _line_observations(
        self,
        action: str,
        value: int,
        dx: int,
        dy: int,
        before_values: tuple[int, ...],
    ) -> int:
        return sum(
            rule.observations
            for rule in self.active_line_rules(action)
            if rule.anchor_value == value
            and rule.dx == dx
            and rule.dy == dy
            and rule.before_values == before_values
        )

    def _context_observations(self, context: tuple) -> int:
        value, action, dx, dy, before_values = context
        return self.context_attempts.get(self._context_key(context), 0) + self._line_observations(
            str(action), int(value), int(dx), int(dy), tuple(before_values)
        )

    def _context_key(self, context: tuple) -> str:
        return repr(context)

    def _default_store_path(self) -> Path:
        if self.output_path == DEFAULT_OUTPUT_PATH:
            return DEFAULT_STORE_PATH
        return self.output_path.with_suffix(".json")

    def _default_journal_path(self) -> Path:
        if self.output_path == DEFAULT_OUTPUT_PATH:
            return DEFAULT_JOURNAL_PATH
        return self.output_path.with_name(f"{self.output_path.stem}_journal.md")

    def _load(self) -> None:
        if not self.store_path.exists():
            return

        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.context_attempts = {
            str(item["context"]): int(item.get("attempts", 0))
            for item in data.get("context_attempts", [])
        }
        self.action_deltas = {
            (str(item["action"]), int(item["value"])): (
                int(item["dx"]),
                int(item["dy"]),
            )
            for item in data.get("action_deltas", [])
        }
        self.rules = [
            StrictRule(
                id=str(item["id"]),
                action=str(item["action"]),
                before=RawFrame.from_grid(item["before"]),
                after=RawFrame.from_grid(item["after"]),
                changed_cells=tuple(
                    tuple(int(value) for value in change)  # type: ignore[misc]
                    for change in item.get("changed_cells", [])
                ),
                status=str(item.get("status", "active")),
                observations=int(item.get("observations", 1)),
                prediction_hits=int(item.get("prediction_hits", 0)),
                prediction_failures=[
                    str(failure) for failure in item.get("prediction_failures", [])
                ],
            )
            for item in data.get("rules", [])
        ]
        self.line_rules = [
            RawLineRule(
                id=str(item["id"]),
                action=str(item["action"]),
                anchor_value=int(item["anchor_value"]),
                dx=int(item["dx"]),
                dy=int(item["dy"]),
                before_values=tuple(int(value) for value in item["before_values"]),
                after_values=tuple(int(value) for value in item["after_values"]),
                status=str(item.get("status", "active")),
                observations=int(item.get("observations", 1)),
                prediction_hits=int(item.get("prediction_hits", 0)),
                prediction_failures=[
                    str(failure) for failure in item.get("prediction_failures", [])
                ],
            )
            for item in data.get("line_rules", [])
        ]
        self.failures = [
            PredictionFailure(
                action=str(item["action"]),
                expected_rule_ids=tuple(
                    str(rule_id) for rule_id in item.get("expected_rule_ids", [])
                ),
                observed_changes=tuple(
                    tuple(int(value) for value in change)  # type: ignore[misc]
                    for change in item.get("observed_changes", [])
                ),
            )
            for item in data.get("failures", [])
        ]
        self._next_id = int(data.get("next_id", self._next_id))
        highest_existing_id = self._highest_existing_rule_number()
        if self._next_id <= highest_existing_id:
            self._next_id = highest_existing_id + 1
        self._next_line_id = int(data.get("next_line_id", self._next_line_id))
        highest_line_id = self._highest_existing_line_rule_number()
        if self._next_line_id <= highest_line_id:
            self._next_line_id = highest_line_id + 1
        self.loaded_rule_count = len(self.rules)
        if self.loaded_rule_count or self.line_rules:
            self._append_journal(
                f"loaded {self.loaded_rule_count} persisted transition rules and "
                f"{len(self.line_rules)} line rules from {self.store_path}"
            )

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._to_data(), indent=2),
            encoding="utf-8",
        )

    def _to_data(self) -> dict:
        return {
            "version": 1,
            "next_id": self._next_id,
            "next_line_id": self._next_line_id,
            "context_attempts": [
                {"context": context, "attempts": attempts}
                for context, attempts in sorted(self.context_attempts.items())
            ],
            "action_deltas": [
                {
                    "action": action,
                    "value": value,
                    "dx": dx,
                    "dy": dy,
                }
                for (action, value), (dx, dy) in sorted(self.action_deltas.items())
            ],
            "rules": [
                {
                    "id": rule.id,
                    "action": rule.action,
                    "before": self._frame_to_data(rule.before),
                    "after": self._frame_to_data(rule.after),
                    "changed_cells": [list(change) for change in rule.changed_cells],
                    "status": rule.status,
                    "observations": rule.observations,
                    "prediction_hits": rule.prediction_hits,
                    "prediction_failures": list(rule.prediction_failures),
                }
                for rule in self.rules
            ],
            "line_rules": [
                {
                    "id": rule.id,
                    "action": rule.action,
                    "anchor_value": rule.anchor_value,
                    "dx": rule.dx,
                    "dy": rule.dy,
                    "before_values": list(rule.before_values),
                    "after_values": list(rule.after_values),
                    "status": rule.status,
                    "observations": rule.observations,
                    "prediction_hits": rule.prediction_hits,
                    "prediction_failures": list(rule.prediction_failures),
                }
                for rule in self.line_rules
            ],
            "failures": [
                {
                    "action": failure.action,
                    "expected_rule_ids": list(failure.expected_rule_ids),
                    "observed_changes": [
                        list(change) for change in failure.observed_changes
                    ],
                }
                for failure in self.failures
            ],
        }

    def _frame_to_data(self, frame: RawFrame) -> list[list[int]]:
        return [list(row) for row in frame.grid]

    def _highest_existing_rule_number(self) -> int:
        highest = 0
        for rule in self.rules:
            if len(rule.id) > 1 and rule.id[0] == "R" and rule.id[1:].isdigit():
                highest = max(highest, int(rule.id[1:]))
        return highest

    def _highest_existing_line_rule_number(self) -> int:
        highest = 0
        for rule in self.line_rules:
            if len(rule.id) > 1 and rule.id[0] == "L" and rule.id[1:].isdigit():
                highest = max(highest, int(rule.id[1:]))
        return highest

    def _append_journal(self, event: str) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.journal_path.exists():
            self.journal_path.write_text(
                "# Strict Parameterless LIVE Rule Growth Journal\n\n",
                encoding="utf-8",
            )
        timestamp = datetime.now().isoformat(timespec="seconds")
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(f"- {timestamp} - {event}\n")

    def _render(self, final: bool, extra_sections: list[str]) -> str:
        lines = [
            "# Strict Parameterless LIVE",
            "",
            "This file records a raw-state limitation experiment.",
            "The interface is parameterless actions over raw integer frames.",
            "No action parameters were provided; actions are opaque names such as ACTION1.",
            "Rules are changed-cell hypothesis records learned from observed transitions.",
            f"Persistent rule store: `{self.store_path}`.",
            f"Append-only growth journal: `{self.journal_path}`.",
            f"Loaded persisted rules at start: {self.loaded_rule_count}.",
            "",
            "## Learned Action Deltas",
            "",
        ]
        if not self.action_deltas:
            lines.append("- None yet.")
        for (action, value), (dx, dy) in sorted(self.action_deltas.items()):
            lines.append(f"- ActionDelta({action},{value},{dx},{dy})")

        lines.extend(["", "## Tested Interaction Contexts", ""])
        if not self.context_attempts:
            lines.append("- None yet.")
        for context, attempts in sorted(self.context_attempts.items()):
            lines.append(f"- {context}: {attempts}")

        lines.extend(
            [
                "",
                "## Active Raw Line Rules",
                "",
            ]
        )
        active_line_rules = self.active_line_rules()
        if not active_line_rules:
            lines.append("- None yet.")
        for rule in active_line_rules:
            lines.extend(
                [
                    f"### {rule.id}",
                    "",
                    f"- action: {rule.action}",
                    f"- anchor_value: {rule.anchor_value}",
                    f"- delta: ({rule.dx},{rule.dy})",
                    f"- before_line: {rule.before_values}",
                    f"- after_line: {rule.after_values}",
                    f"- observations: {rule.observations}",
                    f"- prediction_hits: {rule.prediction_hits}",
                    "",
                ]
            )

        lines.extend(
            [
                "",
                "## Active Rules",
                "",
            ]
        )
        active = self.active_rules()
        if not active:
            lines.append("- No active rules yet.")
        for rule in active:
            lines.extend(self._render_rule(rule))

        lines.extend(["", "## Retired Or Replaced Rules", "", "- None in this strict run."])
        lines.extend(["", "## Prediction Failures", ""])
        if not self.failures:
            lines.append("- None recorded.")
        for index, failure in enumerate(self.failures, start=1):
            lines.append(
                f"- F{index:03d}: action={failure.action}, rules={failure.expected_rule_ids}, "
                f"observed_changes={failure.observed_changes}"
            )

        lines.extend(["", "## Limitations Observed", ""])
        lines.extend(
            [
                "- The model starts with no transition knowledge.",
                "- It can only reuse exact raw transitions and raw changed-cell hypotheses.",
                "- It has no supplied object vocabulary, no action parameters, and no domain rule text.",
                "- A goal cell value can be recognized, but the model is not told what that value means.",
            ]
        )

        if extra_sections:
            lines.extend(["", *extra_sections])

        if final:
            lines.extend(["", "## Final Rule Set", ""])
            if not active and not active_line_rules:
                lines.append("- No final active rules.")
            for rule in active:
                lines.append(
                    f"- {rule.id}: action={rule.action}, changed_cells={rule.changed_cells}, "
                    f"observations={rule.observations}, hits={rule.prediction_hits}"
                )
            for rule in active_line_rules:
                lines.append(
                    f"- {rule.id}: action={rule.action}, before_line={rule.before_values}, "
                    f"after_line={rule.after_values}, delta=({rule.dx},{rule.dy}), "
                    f"observations={rule.observations}, hits={rule.prediction_hits}"
                )

        return "\n".join(lines) + "\n"

    def _render_rule(self, rule: StrictRule) -> list[str]:
        lines = [
            f"### {rule.id}",
            "",
            f"- status: {rule.status}",
            f"- action: {rule.action}",
            f"- observations: {rule.observations}",
            f"- prediction_hits: {rule.prediction_hits}",
            f"- changed_cells: {rule.changed_cells}",
            "- before:",
            *[f"  - `{line}`" for line in rule.before.to_lines()],
            "- after:",
            *[f"  - `{line}`" for line in rule.after.to_lines()],
        ]
        if rule.prediction_failures:
            lines.append("- prediction_failures:")
            lines.extend(f"  - {failure}" for failure in rule.prediction_failures)
        lines.append("")
        return lines
