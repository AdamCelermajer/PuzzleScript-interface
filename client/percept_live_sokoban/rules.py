from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from client.engine.types import GameAction

from .model import SymbolFrame


DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent / "output" / "percept_live_rules.md"
)
DEFAULT_STORE_PATH = (
    Path(__file__).resolve().parent / "output" / "percept_live_rules.json"
)
DEFAULT_JOURNAL_PATH = (
    Path(__file__).resolve().parent / "output" / "percept_live_journal.md"
)


def _action_name(action: GameAction | str) -> str:
    return action.name if isinstance(action, GameAction) else str(action)


@dataclass
class SymbolLineRule:
    id: str
    action: str
    anchor_symbol: str
    dx: int
    dy: int
    before_symbols: tuple[str, ...]
    after_symbols: tuple[str, ...]
    status: str = "active"
    observations: int = 1
    prediction_hits: int = 0
    prediction_failures: list[str] = field(default_factory=list)

    def predictions(self, frame: SymbolFrame) -> list[SymbolFrame]:
        predictions = []
        for x, y in frame.positions(self.anchor_symbol):
            before_line = frame.line(x, y, self.dx, self.dy, len(self.before_symbols))
            if before_line != self.before_symbols:
                continue
            predicted = frame.apply_line(x, y, self.dx, self.dy, self.after_symbols)
            if predicted is not None:
                predictions.append(predicted)
        return predictions


@dataclass
class PerceptFailure:
    action: str
    expected_rule_ids: tuple[str, ...]
    observed_before: list[str]
    observed_after: list[str]


class PerceptRuleModel:
    """Learns action effects over PuzzleScript symbols and coordinates."""

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
        self.action_deltas: dict[tuple[str, str], tuple[int, int]] = {}
        self.context_attempts: dict[str, int] = {}
        self.rules: list[SymbolLineRule] = []
        self.failures: list[PerceptFailure] = []
        self._next_id = 1
        self.loaded_rule_count = 0
        if load_existing:
            self._load()

    def observe(
        self, before: SymbolFrame, action: GameAction | str, after: SymbolFrame
    ) -> None:
        action_name = _action_name(action)
        learned_deltas = self._learn_action_deltas(before, action_name, after)
        candidate_deltas = [
            (symbol, dx, dy)
            for (known_action, symbol), (dx, dy) in self.action_deltas.items()
            if known_action == action_name
        ]

        for symbol, dx, dy in candidate_deltas:
            rule = self._line_rule_from_transition(
                before, action_name, after, symbol, dx, dy
            )
            if rule is None:
                continue
            existing = self._find_matching_rule(rule)
            if existing is not None:
                existing.observations += 1
                self._append_journal(
                    f"observed existing {existing.id}: action={action_name}, "
                    f"observations={existing.observations}"
                )
            else:
                self.rules.append(rule)
                self._append_journal(
                    f"created {rule.id}: action={action_name}, "
                    f"line={rule.before_symbols}->{rule.after_symbols}, "
                    f"delta=({rule.dx},{rule.dy})"
                )

        if learned_deltas or candidate_deltas:
            self._save()
            self.write()

    def predict(self, before: SymbolFrame, action: GameAction | str) -> list[SymbolFrame]:
        action_name = _action_name(action)
        predictions: list[SymbolFrame] = []
        seen: set[SymbolFrame] = set()
        for rule in self.active_rules(action_name):
            for predicted in rule.predictions(before):
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

        action_name = _action_name(action)
        matching = [
            rule
            for rule in self.active_rules(action_name)
            if after in rule.predictions(before)
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

        expected_ids = tuple(
            rule.id
            for rule in self.active_rules(action_name)
            if any(predicted in predictions for predicted in rule.predictions(before))
        )
        failure = PerceptFailure(
            action=action_name,
            expected_rule_ids=expected_ids,
            observed_before=before.to_rows(),
            observed_after=after.to_rows(),
        )
        self.failures.append(failure)
        for rule in self.rules:
            if rule.id in expected_ids:
                rule.prediction_failures.append(
                    f"observed {before.to_rows()} -> {after.to_rows()}"
                )
        self._save()
        self._append_journal(
            f"prediction failure: action={action_name}, rules={expected_ids}"
        )
        self.write()

    def active_rules(self, action: str | None = None) -> list[SymbolLineRule]:
        return [
            rule
            for rule in self.rules
            if rule.status == "active" and (action is None or rule.action == action)
        ]

    def action_has_delta(self, action: GameAction) -> bool:
        action_name = _action_name(action)
        return any(known_action == action_name for known_action, _symbol in self.action_deltas)

    def unseen_context_action(
        self, frame: SymbolFrame, actions: list[GameAction]
    ) -> tuple[GameAction, tuple[str, str, int, int, tuple[str, ...]]] | None:
        for action in actions:
            action_name = _action_name(action)
            for (known_action, symbol), (dx, dy) in sorted(self.action_deltas.items()):
                if known_action != action_name:
                    continue
                for x, y in frame.positions(symbol):
                    for length in (3, 2):
                        before_symbols = frame.line(x, y, dx, dy, length)
                        if before_symbols is None:
                            continue
                        context = (symbol, action_name, dx, dy, before_symbols)
                        if self._context_observations(context) == 0:
                            return action, (
                                symbol,
                                action_name,
                                dx,
                                dy,
                                before_symbols,
                            )
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

    def _learn_action_deltas(
        self, before: SymbolFrame, action: str, after: SymbolFrame
    ) -> list[tuple[str, int, int]]:
        learned = []
        symbols = {
            symbol
            for row in before.grid
            for symbol in row
            if symbol != "."
        } | {
            symbol
            for row in after.grid
            for symbol in row
            if symbol != "."
        }

        for symbol in sorted(symbols):
            before_positions = set(before.positions(symbol))
            after_positions = set(after.positions(symbol))
            vanished = before_positions - after_positions
            emerged = after_positions - before_positions
            for old_x, old_y in vanished:
                for new_x, new_y in emerged:
                    dx = new_x - old_x
                    dy = new_y - old_y
                    if abs(dx) + abs(dy) != 1:
                        continue
                    key = (action, symbol)
                    if key not in self.action_deltas:
                        self.action_deltas[key] = (dx, dy)
                        learned.append((symbol, dx, dy))
                        self._append_journal(
                            f"created ActionDelta({action},{symbol},{dx},{dy})"
                        )
        return learned

    def _line_rule_from_transition(
        self,
        before: SymbolFrame,
        action: str,
        after: SymbolFrame,
        anchor_symbol: str,
        dx: int,
        dy: int,
    ) -> SymbolLineRule | None:
        anchors = before.positions(anchor_symbol)
        if not anchors:
            return None

        changed = set(before.changed_positions(after))
        for x, y in anchors:
            if changed:
                line_indexes = self._changed_line_indexes(changed, x, y, dx, dy)
                if line_indexes is None:
                    continue
                length = max(2, min(3, max(line_indexes) + 1))
            else:
                length = 2

            before_line = before.line(x, y, dx, dy, length)
            after_line = after.line(x, y, dx, dy, length)
            if before_line is None or after_line is None:
                continue
            if before_line == after_line and changed:
                continue
            return SymbolLineRule(
                id=self._new_rule_id(),
                action=action,
                anchor_symbol=anchor_symbol,
                dx=dx,
                dy=dy,
                before_symbols=before_line,
                after_symbols=after_line,
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

    def _find_matching_rule(self, candidate: SymbolLineRule) -> SymbolLineRule | None:
        for rule in self.rules:
            if (
                rule.action == candidate.action
                and rule.anchor_symbol == candidate.anchor_symbol
                and rule.dx == candidate.dx
                and rule.dy == candidate.dy
                and rule.before_symbols == candidate.before_symbols
                and rule.after_symbols == candidate.after_symbols
            ):
                return rule
        return None

    def _line_observations(
        self,
        action: str,
        symbol: str,
        dx: int,
        dy: int,
        before_symbols: tuple[str, ...],
    ) -> int:
        return sum(
            rule.observations
            for rule in self.active_rules(action)
            if rule.anchor_symbol == symbol
            and rule.dx == dx
            and rule.dy == dy
            and rule.before_symbols == before_symbols
        )

    def _context_observations(self, context: tuple) -> int:
        symbol, action, dx, dy, before_symbols = context
        return self.context_attempts.get(self._context_key(context), 0) + self._line_observations(
            str(action), str(symbol), int(dx), int(dy), tuple(before_symbols)
        )

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

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.context_attempts = {
            str(item["context"]): int(item.get("attempts", 0))
            for item in data.get("context_attempts", [])
        }
        self.action_deltas = {
            (str(item["action"]), str(item["symbol"])): (
                int(item["dx"]),
                int(item["dy"]),
            )
            for item in data.get("action_deltas", [])
        }
        self.rules = [
            SymbolLineRule(
                id=str(item["id"]),
                action=str(item["action"]),
                anchor_symbol=str(item["anchor_symbol"]),
                dx=int(item["dx"]),
                dy=int(item["dy"]),
                before_symbols=tuple(str(symbol) for symbol in item["before_symbols"]),
                after_symbols=tuple(str(symbol) for symbol in item["after_symbols"]),
                status=str(item.get("status", "active")),
                observations=int(item.get("observations", 1)),
                prediction_hits=int(item.get("prediction_hits", 0)),
                prediction_failures=[
                    str(failure) for failure in item.get("prediction_failures", [])
                ],
            )
            for item in data.get("rules", [])
        ]
        self.failures = [
            PerceptFailure(
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
            f"loaded {self.loaded_rule_count} persisted symbol rules from {self.store_path}"
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
            "context_attempts": [
                {"context": context, "attempts": attempts}
                for context, attempts in sorted(self.context_attempts.items())
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
                    "anchor_symbol": rule.anchor_symbol,
                    "dx": rule.dx,
                    "dy": rule.dy,
                    "before_symbols": list(rule.before_symbols),
                    "after_symbols": list(rule.after_symbols),
                    "status": rule.status,
                    "observations": rule.observations,
                    "prediction_hits": rule.prediction_hits,
                    "prediction_failures": list(rule.prediction_failures),
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
                "# Symbol Percept LIVE Rule Growth Journal\n\n",
                encoding="utf-8",
            )
        timestamp = datetime.now().isoformat(timespec="seconds")
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(f"- {timestamp} - {event}\n")

    def _render(self, final: bool, extra_sections: list[str]) -> str:
        lines = [
            "# Symbol Percept LIVE Sokoban",
            "",
            "State is represented as PuzzleScript symbols and coordinate facts.",
            "The model is not given human object names or action directions.",
            f"Persistent rule store: `{self.store_path}`.",
            f"Append-only growth journal: `{self.journal_path}`.",
            f"Loaded persisted line rules at start: {self.loaded_rule_count}.",
            "",
            "## Learned Action Deltas",
            "",
        ]
        if not self.action_deltas:
            lines.append("- None yet.")
        for (action, symbol), (dx, dy) in sorted(self.action_deltas.items()):
            lines.append(f"- ActionDelta({action},{symbol},{dx},{dy})")

        lines.extend(["", "## Tested Interaction Contexts", ""])
        if not self.context_attempts:
            lines.append("- None yet.")
        for context, attempts in sorted(self.context_attempts.items()):
            lines.append(f"- {context}: {attempts}")

        lines.extend(["", "## Active Symbol Line Rules", ""])
        active = self.active_rules()
        if not active:
            lines.append("- None yet.")
        for rule in active:
            lines.extend(
                [
                    f"### {rule.id}",
                    "",
                    f"- action: {rule.action}",
                    f"- anchor_symbol: {rule.anchor_symbol}",
                    f"- delta: ({rule.dx},{rule.dy})",
                    f"- before_line: {rule.before_symbols}",
                    f"- after_line: {rule.after_symbols}",
                    f"- observations: {rule.observations}",
                    f"- prediction_hits: {rule.prediction_hits}",
                    "",
                ]
            )

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
                lines.append(
                    f"- {rule.id}: {rule.action} {rule.before_symbols} -> "
                    f"{rule.after_symbols} by ({rule.dx},{rule.dy})"
                )

        return "\n".join(lines) + "\n"
