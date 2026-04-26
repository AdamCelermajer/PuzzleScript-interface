from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from client.engine.types import GameAction
from client.live_sokoban_poc.model import (
    ACTION_DELTAS,
    BoardState,
    Position,
    add_pos,
)


ANY_DIRECTION = "ANY_DIRECTION"


class RuleStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass
class RuleApplication:
    action: str
    before_player: Position
    after_player: Position
    success: bool
    note: str = ""


@dataclass
class Rule:
    rule_id: str
    conditions: tuple[str, ...]
    action: str
    effect: str
    emerged: tuple[str, ...]
    vanished: tuple[str, ...]
    source: str
    status: RuleStatus = RuleStatus.ACTIVE
    sibling_id: str | None = None
    retired_reason: str | None = None
    replacement_id: str | None = None
    applications: list[RuleApplication] = field(default_factory=list)

    def equivalent_to(self, other: "Rule") -> bool:
        return (
            self.status == RuleStatus.ACTIVE
            and self.conditions == other.conditions
            and self.action == other.action
            and self.effect == other.effect
        )


@dataclass
class Prediction:
    board: BoardState
    rule_id: str
    expected_emerged: tuple[str, ...]
    expected_vanished: tuple[str, ...]


class RuleModel:
    def __init__(self, output_path: str | Path | None = None) -> None:
        self.rules: dict[str, Rule] = {}
        self.events: list[str] = []
        self.timeline: list[str] = []
        self.failures: list[str] = []
        self.output_path = Path(output_path) if output_path is not None else None
        self._next_rule_number = 1

    @property
    def active_rules(self) -> list[Rule]:
        return [rule for rule in self.rules.values() if rule.status == RuleStatus.ACTIVE]

    def add_rule(self, rule: Rule) -> Rule:
        if not rule.rule_id:
            rule.rule_id = self._new_rule_id()
        else:
            self._next_rule_number = max(
                self._next_rule_number, int(rule.rule_id[1:]) + 1
            )
        self.rules[rule.rule_id] = rule
        self._record_event(f"created {rule.rule_id}: {rule.effect}")
        self.write_rule_file()
        return rule

    def learn_from_transition(
        self, before: BoardState, action: GameAction, after: BoardState
    ) -> Rule:
        new_rule = build_rule_from_transition(
            self._new_rule_id(), before, action, after, source="observed transition"
        )
        existing = self._find_equivalent_rule(new_rule)
        if existing is not None:
            existing.applications.append(_application(before, after, action, True))
            self._record_event(f"merged observation into {existing.rule_id}")
            self.write_rule_file()
            return existing

        new_rule.applications.append(_application(before, after, action, True))
        self.rules[new_rule.rule_id] = new_rule
        self._record_event(f"created {new_rule.rule_id}: {new_rule.effect}")
        self.write_rule_file()
        return new_rule

    def predict(self, before: BoardState, action: GameAction) -> Prediction | None:
        for rule in self.active_rules:
            if rule.action not in {action.name, ANY_DIRECTION}:
                continue
            if not conditions_match(rule.conditions, before, action):
                continue
            board = apply_rule_effect(rule.effect, before, action)
            return Prediction(
                board=board,
                rule_id=rule.rule_id,
                expected_emerged=rule.emerged,
                expected_vanished=rule.vanished,
            )
        return None

    def revise_after_failure(
        self,
        faulty_rule: Rule,
        before: BoardState,
        action: GameAction,
        actual_after: BoardState,
    ) -> Rule:
        self.failures.append(
            f"{faulty_rule.rule_id} predicted the wrong result for {action.name} "
            f"from player {before.player}"
        )
        replacement = build_rule_from_transition(
            self._new_rule_id(),
            before,
            action,
            actual_after,
            source=f"prediction failure from {faulty_rule.rule_id}",
        )
        replacement.sibling_id = faulty_rule.rule_id
        replacement.applications.append(_application(before, actual_after, action, True))
        self.rules[replacement.rule_id] = replacement

        faulty_rule.sibling_id = replacement.rule_id
        faulty_rule.applications.append(_application(before, actual_after, action, False))
        self.retire_rule(
            faulty_rule, reason="specialized_by", replacement_id=replacement.rule_id
        )
        self._record_event(
            f"split {faulty_rule.rule_id} into sibling {replacement.rule_id}"
        )
        self.write_rule_file()
        return replacement

    def record_success(
        self, rule_id: str, before: BoardState, action: GameAction, after: BoardState
    ) -> None:
        rule = self.rules[rule_id]
        rule.applications.append(_application(before, after, action, True))
        self.write_rule_file()

    def retire_rule(
        self, rule: Rule, *, reason: str, replacement_id: str | None = None
    ) -> None:
        rule.status = RuleStatus.RETIRED
        rule.retired_reason = reason
        rule.replacement_id = replacement_id
        self._record_event(
            f"retired {rule.rule_id}: {reason}"
            + (f" {replacement_id}" if replacement_id else "")
        )
        self.write_rule_file()

    def write_rule_file(self, *, final: bool = False) -> None:
        if self.output_path is None:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(self.to_markdown(final=final), encoding="utf-8")

    def to_markdown(self, *, final: bool = False) -> str:
        lines = [
            "# Sokoban LIVE Rule Model",
            "",
            "Game: `ps_sokoban_basic-v1`, level 1",
            "Goal: crates on `(2, 1)` and `(1, 3)`",
            "",
            "## Active Rules",
            "",
        ]
        lines.extend(_format_rule(rule) for rule in self.active_rules)
        if not self.active_rules:
            lines.append("(none)")

        retired = [rule for rule in self.rules.values() if rule.status == RuleStatus.RETIRED]
        lines.extend(["", "## Retired / Replaced Rules", ""])
        lines.extend(_format_rule(rule) for rule in retired)
        if not retired:
            lines.append("(none)")

        lines.extend(["", "## Prediction Failures", ""])
        lines.extend(f"- {failure}" for failure in self.failures)
        if not self.failures:
            lines.append("(none)")

        lines.extend(["", "## Merge / Revision History", ""])
        lines.extend(f"- {event}" for event in self.events)
        if not self.events:
            lines.append("(none)")

        lines.extend(["", "## Rule Timeline", ""])
        lines.extend(f"- {snapshot}" for snapshot in self.timeline)
        if not self.timeline:
            lines.append("(none)")

        if final:
            lines.extend(["", "## Final Rule Set", ""])
            active = self.active_rules
            lines.extend(_format_rule(rule) for rule in active)
            if not active:
                lines.append("(none)")

        return "\n".join(lines) + "\n"

    def _new_rule_id(self) -> str:
        rule_id = f"R{self._next_rule_number:03d}"
        self._next_rule_number += 1
        return rule_id

    def _find_equivalent_rule(self, candidate: Rule) -> Rule | None:
        for rule in self.active_rules:
            if rule.equivalent_to(candidate):
                return rule
        return None

    def _record_event(self, message: str) -> None:
        self.events.append(message)
        active = ", ".join(
            f"{rule.rule_id}:{rule.effect}" for rule in self.active_rules
        )
        retired = ", ".join(
            rule.rule_id
            for rule in self.rules.values()
            if rule.status == RuleStatus.RETIRED
        )
        self.timeline.append(
            f"{message} | active=[{active or '-'}] | retired=[{retired or '-'}]"
        )


def build_rule_from_transition(
    rule_id: str,
    before: BoardState,
    action: GameAction,
    after: BoardState,
    *,
    source: str,
) -> Rule:
    before_facts = before.facts()
    after_facts = after.facts()
    emerged = tuple(sorted(after_facts - before_facts))
    vanished = tuple(sorted(before_facts - after_facts))
    conditions, effect = explain_transition(before, action, after)
    return Rule(
        rule_id=rule_id,
        conditions=conditions,
        action=ANY_DIRECTION,
        effect=effect,
        emerged=emerged,
        vanished=vanished,
        source=source,
    )


def explain_transition(
    before: BoardState, action: GameAction, after: BoardState
) -> tuple[tuple[str, ...], str]:
    delta = ACTION_DELTAS[action]
    front = add_pos(before.player, delta)
    behind = add_pos(front, delta)

    if after == before:
        if front in before.crates:
            if behind in before.crates or behind in before.walls or not before.is_inside(behind):
                return ("FrontIsCrate", "BehindCrateIsBlocked"), "blocked"
        if front in before.walls or not before.is_inside(front):
            return ("FrontIsWall",), "blocked"
        return ("NoObservedChange",), "blocked"

    if front in before.crates and behind in after.crates:
        return ("FrontIsCrate", "BehindCrateIsFree"), "push_crate"

    return ("FrontIsFree",), "move_player"


def conditions_match(
    conditions: tuple[str, ...], board: BoardState, action: GameAction
) -> bool:
    delta = ACTION_DELTAS.get(action)
    if delta is None:
        return False

    front = add_pos(board.player, delta)
    behind = add_pos(front, delta)

    for condition in conditions:
        if condition == "Always":
            continue
        if condition == "FrontIsFree" and board.is_blocked(front):
            return False
        if condition == "FrontIsCrate" and front not in board.crates:
            return False
        if condition == "BehindCrateIsFree" and board.is_blocked(behind):
            return False
        if condition == "BehindCrateIsBlocked" and not board.is_blocked(behind):
            return False
        if condition == "FrontIsWall" and front not in board.walls:
            return False
        if condition == "NoObservedChange":
            return False
    return True


def apply_rule_effect(
    effect: str, board: BoardState, action: GameAction
) -> BoardState:
    delta = ACTION_DELTAS[action]
    front = add_pos(board.player, delta)
    behind = add_pos(front, delta)

    if effect == "blocked":
        return board
    if effect == "push_crate" and front in board.crates:
        crates = set(board.crates)
        crates.remove(front)
        crates.add(behind)
        return board.with_changes(player=front, crates=frozenset(crates))
    if effect == "move_player":
        return board.with_changes(player=front)
    return board


def _application(
    before: BoardState, after: BoardState, action: GameAction, success: bool
) -> RuleApplication:
    return RuleApplication(
        action=action.name,
        before_player=before.player,
        after_player=after.player,
        success=success,
    )


def _format_rule(rule: Rule) -> str:
    sibling = rule.sibling_id or "-"
    replacement = rule.replacement_id or "-"
    retired_reason = rule.retired_reason or "-"
    applications = len(rule.applications)
    emerged = ", ".join(rule.emerged[:6]) or "-"
    vanished = ", ".join(rule.vanished[:6]) or "-"
    return "\n".join(
        [
            f"### {rule.rule_id} [{rule.status.value}]",
            f"- action: `{rule.action}`",
            f"- conditions: `{', '.join(rule.conditions)}`",
            f"- effect: `{rule.effect}`",
            f"- sibling: `{sibling}`",
            f"- retired_reason: `{retired_reason}`",
            f"- replacement: `{replacement}`",
            f"- source: {rule.source}",
            f"- applications: {applications}",
            f"- emerged: {emerged}",
            f"- vanished: {vanished}",
            "",
        ]
    )
