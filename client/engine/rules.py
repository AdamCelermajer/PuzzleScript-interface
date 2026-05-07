from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from client.engine.history import TransitionRecord
from client.engine.rule_schema import GeneralizedRule
from client.engine.state import EngineState
from client.engine.types import GameAction


@dataclass
class RuleEntry:
    id: str
    kind: str
    status: str
    text: str
    before: EngineState | None = None
    action: str | None = None
    after: EngineState | None = None
    source_transition_ids: list[str] = field(default_factory=list)
    observations: int = 0
    prediction_hits: int = 0
    prediction_failures: int = 0
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "RuleEntry":
        before = data.get("before")
        after = data.get("after")
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            status=str(data["status"]),
            text=str(data.get("text", "")),
            before=EngineState.from_data(before) if before else None,
            action=str(data["action"]) if data.get("action") else None,
            after=EngineState.from_data(after) if after else None,
            source_transition_ids=[
                str(value) for value in data.get("source_transition_ids", [])
            ],
            observations=int(data.get("observations", 0)),
            prediction_hits=int(data.get("prediction_hits", 0)),
            prediction_failures=int(data.get("prediction_failures", 0)),
            notes=[str(value) for value in data.get("notes", [])],
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "text": self.text,
            "before": self.before.to_data() if self.before else None,
            "action": self.action,
            "after": self.after.to_data() if self.after else None,
            "source_transition_ids": list(self.source_transition_ids),
            "observations": self.observations,
            "prediction_hits": self.prediction_hits,
            "prediction_failures": self.prediction_failures,
            "notes": list(self.notes),
        }

    def can_predict(self) -> bool:
        return (
            self.kind == "transition"
            and self.status == "verified"
            and self.before is not None
            and self.action is not None
            and self.after is not None
        )


class RuleLibrary:
    """Readable rule store with strict separation between hypotheses and executables."""

    def __init__(self, base_path: str | Path, load_existing: bool = True) -> None:
        self.base_path = Path(base_path)
        self.json_path = self.base_path / "rules.json"
        self.markdown_path = self.base_path / "rules.md"
        self.journal_path = self.base_path / "journal.md"
        self.generalized_json_path = self.base_path / "rules_v2.json"
        self.generalized_markdown_path = self.base_path / "rules_v2.md"
        self.generalized_journal_path = self.base_path / "journal_v2.md"
        self.rules: list[RuleEntry] = []
        self.generalized_rules: list[GeneralizedRule] = []
        self._next_id = 1
        self._next_generalized_id = 1
        if load_existing:
            self._load()
            self._load_generalized()

    def add_hypotheses(
        self, hypotheses: list[str], source: TransitionRecord
    ) -> list[RuleEntry]:
        added: list[RuleEntry] = []
        for hypothesis in hypotheses:
            text = hypothesis.strip()
            if not text:
                continue
            existing = self._find_hypothesis(text, source.id)
            if existing is not None:
                added.append(existing)
                continue
            rule = RuleEntry(
                id=self._new_id("H"),
                kind="hypothesis",
                status="proposed",
                text=text,
                source_transition_ids=[source.id],
            )
            self.rules.append(rule)
            added.append(rule)
            self._append_journal(f"proposed {rule.id}: {text}")
        if added:
            self._save()
            self.write_markdown()
        return added

    def record_transition(self, record: TransitionRecord) -> RuleEntry:
        exact = self._find_exact_transition(record)
        if exact is not None:
            exact.observations += 1
            if record.id not in exact.source_transition_ids:
                exact.source_transition_ids.append(record.id)
            self._append_journal(
                f"observed existing {exact.id}: {record.action.name}, "
                f"observations={exact.observations}"
            )
            self._save()
            self.write_markdown()
            return exact

        for conflicting in self._transition_rules(record.before, record.action):
            if conflicting.after != record.after:
                conflicting.status = "rejected"
                conflicting.prediction_failures += 1
                conflicting.notes.append(f"conflicted with {record.id}")

        rule = RuleEntry(
            id=self._new_id("R"),
            kind="transition",
            status="verified",
            text=f"{record.action.name}: state-specific observed transition",
            before=record.before,
            action=record.action.name,
            after=record.after,
            source_transition_ids=[record.id],
            observations=1,
        )
        self.rules.append(rule)
        self._append_journal(f"created transition memory {rule.id}: {rule.text}")
        self._save()
        self.write_markdown()
        return rule

    def predict(self, before: EngineState, action: GameAction) -> list[EngineState]:
        generalized = self._generalized_predictions(before, action)
        if generalized:
            return generalized

        predictions: list[EngineState] = []
        seen: set[EngineState] = set()
        for rule in self._transition_rules(before, action):
            if not rule.can_predict() or rule.after is None:
                continue
            if rule.after in seen:
                continue
            predictions.append(rule.after)
            seen.add(rule.after)
        return predictions

    def add_generalized_rule(self, rule: GeneralizedRule) -> GeneralizedRule:
        prepared = rule
        if not prepared.id:
            prepared = prepared.with_id(self._new_generalized_id())
        existing = self._find_generalized_equivalent(prepared)
        if existing is not None:
            return existing
        self.generalized_rules.append(prepared)
        self._append_generalized_journal(
            f"stored {prepared.id}: action={prepared.action}, "
            f"status={prepared.status}, evidence={prepared.evidence_ids}"
        )
        self._save_generalized()
        self.write_generalized_markdown()
        return prepared

    def add_generalized_rules(
        self, rules: list[GeneralizedRule]
    ) -> list[GeneralizedRule]:
        added = []
        for rule in rules:
            added.append(self.add_generalized_rule(rule))
        return added

    def record_prediction_result(
        self,
        before: EngineState,
        action: GameAction,
        actual_after: EngineState,
        predictions: list[EngineState],
    ) -> None:
        if not predictions:
            return

        generalized_candidates = self._generalized_prediction_candidates(
            before, action
        )
        if generalized_candidates:
            if actual_after in predictions:
                self._mark_generalized_hits(actual_after, generalized_candidates)
                return
            self._mark_generalized_failures(
                action,
                generalized_candidates,
                f"predicted wrong result for {action.name}",
            )
            return

        rules = self._transition_rules(before, action)
        if actual_after in predictions:
            matched = [
                rule
                for rule in rules
                if rule.status == "verified" and rule.after == actual_after
            ]
            for rule in matched:
                rule.prediction_hits += 1
                self._verify_related_hypotheses(rule)
            self._append_journal(
                f"prediction hit: {action.name}, rules={[rule.id for rule in matched]}"
            )
            self._save()
            self.write_markdown()
            return

        for rule in rules:
            if rule.status != "verified":
                continue
            rule.status = "rejected"
            rule.prediction_failures += 1
            rule.notes.append(f"predicted wrong result for {action.name}")
        self._append_journal(f"prediction failure: {action.name}")
        self._save()
        self.write_markdown()

    def executable_rules(self) -> list[RuleEntry]:
        return [rule for rule in self.rules if rule.can_predict()]

    def hypotheses(self) -> list[RuleEntry]:
        return [rule for rule in self.rules if rule.kind == "hypothesis"]

    def known_rules_text(self) -> str:
        generalized = [
            self._generalized_rule_text(rule)
            for rule in self.generalized_rules
            if rule.status == "verified"
        ]
        verified = [
            rule.text
            for rule in self.rules
            if rule.kind == "hypothesis" and rule.status == "verified"
        ]
        return "\n".join(f"- {rule}" for rule in [*generalized, *verified])

    def write_markdown(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Engine Rule Library",
            "",
            "## Executable State Transitions",
            "",
            *self._render_transitions(),
            "",
            "## LLM Rule Hypotheses",
            "",
            *self._render_hypotheses(),
            "",
            "## Rejected",
            "",
            *self._render_rules("rejected"),
            "",
        ]
        self.markdown_path.write_text("\n".join(lines), encoding="utf-8")

    def write_generalized_markdown(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Engine Generalized Rule Library",
            "",
            "## Verified Executable Rules",
            "",
            *self._render_generalized("verified"),
            "",
            "## Candidate Rules",
            "",
            *self._render_generalized("candidate"),
            "",
            "## Rejected Rules",
            "",
            *self._render_generalized("rejected"),
            "",
        ]
        self.generalized_markdown_path.write_text(
            "\n".join(lines), encoding="utf-8"
        )

    def _render_transitions(self) -> list[str]:
        rendered = []
        for rule in self.rules:
            if rule.kind != "transition" or rule.status != "verified":
                continue
            rendered.append(
                f"- `{rule.id}` {rule.action}: state-specific transition "
                f"observations={rule.observations} "
                f"hits={rule.prediction_hits} failures={rule.prediction_failures}"
            )
        return rendered or ["- none"]

    def _render_hypotheses(self) -> list[str]:
        rendered = []
        for rule in self.rules:
            if rule.kind != "hypothesis" or rule.status == "rejected":
                continue
            rendered.append(
                f"- `{rule.id}` [{rule.status}] {rule.text} "
                f"hits={rule.prediction_hits} failures={rule.prediction_failures}"
            )
        return rendered or ["- none"]

    def _render_rules(self, status: str) -> list[str]:
        rendered = []
        for rule in self.rules:
            if rule.status != status:
                continue
            suffix = (
                f" hits={rule.prediction_hits} failures={rule.prediction_failures}"
            )
            rendered.append(f"- `{rule.id}` [{rule.kind}] {rule.text}{suffix}")
        return rendered or ["- none"]

    def _render_generalized(self, status: str) -> list[str]:
        rendered = []
        for rule in self.generalized_rules:
            if rule.status != status:
                continue
            rendered.append(
                f"- `{rule.id}` {self._generalized_rule_text(rule)} "
                f"hits={rule.prediction_hits} failures={rule.prediction_failures} "
                f"evidence={list(rule.evidence_ids)}"
            )
            for failure in rule.failures:
                rendered.append(f"  - failure: {failure}")
        return rendered or ["- none"]

    def _transition_rules(
        self, before: EngineState, action: GameAction
    ) -> list[RuleEntry]:
        return [
            rule
            for rule in self.rules
            if rule.kind == "transition"
            and rule.before == before
            and rule.action == action.name
        ]

    def _generalized_predictions(
        self, before: EngineState, action: GameAction
    ) -> list[EngineState]:
        predictions: list[EngineState] = []
        seen: set[EngineState] = set()
        for _rule, predicted in self._generalized_prediction_candidates(
            before, action
        ):
            if predicted in seen:
                continue
            predictions.append(predicted)
            seen.add(predicted)
        return predictions

    def _generalized_prediction_candidates(
        self, before: EngineState, action: GameAction
    ) -> list[tuple[GeneralizedRule, EngineState]]:
        candidates: list[tuple[GeneralizedRule, EngineState]] = []
        for rule in self.generalized_rules:
            if rule.status != "verified" or rule.action != action.name:
                continue
            for predicted in rule.predict(before):
                candidates.append((rule, predicted))
        return candidates

    def _mark_generalized_hits(
        self,
        actual_after: EngineState,
        candidates: list[tuple[GeneralizedRule, EngineState]],
    ) -> None:
        changed = False
        for index, (rule, predicted) in enumerate(candidates):
            if predicted != actual_after:
                continue
            replacement = rule.with_hit()
            self._replace_generalized_rule(rule.id, replacement)
            candidates[index] = (replacement, predicted)
            changed = True
        if changed:
            self._append_generalized_journal(
                "prediction hit: "
                f"rules={[rule.id for rule, predicted in candidates if predicted == actual_after]}"
            )
            self._save_generalized()
            self.write_generalized_markdown()

    def _mark_generalized_failures(
        self,
        action: GameAction,
        candidates: list[tuple[GeneralizedRule, EngineState]],
        failure: str,
    ) -> None:
        failed_ids = []
        for rule, _predicted in candidates:
            replacement = rule.with_failure(failure)
            self._replace_generalized_rule(rule.id, replacement)
            failed_ids.append(rule.id)
        if failed_ids:
            self._append_generalized_journal(
                f"prediction failure: action={action.name}, rules={failed_ids}"
            )
            self._save_generalized()
            self.write_generalized_markdown()

    def _find_exact_transition(self, record: TransitionRecord) -> RuleEntry | None:
        return next(
            (
                rule
                for rule in self._transition_rules(record.before, record.action)
                if rule.after == record.after
            ),
            None,
        )

    def _find_hypothesis(self, text: str, source_id: str) -> RuleEntry | None:
        return next(
            (
                rule
                for rule in self.hypotheses()
                if rule.text == text and source_id in rule.source_transition_ids
            ),
            None,
        )

    def _find_generalized_equivalent(
        self, candidate: GeneralizedRule
    ) -> GeneralizedRule | None:
        for rule in self.generalized_rules:
            if (
                rule.action == candidate.action
                and rule.anchor == candidate.anchor
                and rule.conditions == candidate.conditions
                and rule.effects == candidate.effects
                and rule.result_state == candidate.result_state
                and rule.levels_completed == candidate.levels_completed
            ):
                return rule
        return None

    def _replace_generalized_rule(
        self, rule_id: str, replacement: GeneralizedRule
    ) -> None:
        for index, rule in enumerate(self.generalized_rules):
            if rule.id == rule_id:
                self.generalized_rules[index] = replacement
                return

    def _verify_related_hypotheses(self, transition_rule: RuleEntry) -> None:
        sources = set(transition_rule.source_transition_ids)
        for hypothesis in self.hypotheses():
            if not sources.intersection(hypothesis.source_transition_ids):
                continue
            if hypothesis.status != "rejected":
                hypothesis.status = "verified"
                hypothesis.prediction_hits += 1

    def _new_id(self, prefix: str) -> str:
        rule_id = f"{prefix}{self._next_id:06d}"
        self._next_id += 1
        return rule_id

    def _new_generalized_id(self) -> str:
        rule_id = f"G{self._next_generalized_id:06d}"
        self._next_generalized_id += 1
        return rule_id

    def _load(self) -> None:
        if not self.json_path.exists():
            return
        data = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.rules = [RuleEntry.from_data(item) for item in data.get("rules", [])]
        self._next_id = int(data.get("next_id", len(self.rules) + 1))

    def _load_generalized(self) -> None:
        if not self.generalized_json_path.exists():
            return
        data = json.loads(self.generalized_json_path.read_text(encoding="utf-8"))
        self.generalized_rules = [
            GeneralizedRule.from_data(item) for item in data.get("rules", [])
        ]
        self._next_generalized_id = int(
            data.get("next_id", len(self.generalized_rules) + 1)
        )

    def _save(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(
            json.dumps(
                {
                    "next_id": self._next_id,
                    "rules": [rule.to_data() for rule in self.rules],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _save_generalized(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.generalized_json_path.write_text(
            json.dumps(
                {
                    "next_id": self._next_generalized_id,
                    "rules": [rule.to_data() for rule in self.generalized_rules],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _append_journal(self, event: str) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        if not self.journal_path.exists():
            self.journal_path.write_text("# Engine Journal\n\n", encoding="utf-8")
        stamp = datetime.now().isoformat(timespec="seconds")
        with self.journal_path.open("a", encoding="utf-8") as file:
            file.write(f"- {stamp} {event}\n")

    def _append_generalized_journal(self, event: str) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        if not self.generalized_journal_path.exists():
            self.generalized_journal_path.write_text(
                "# Engine Generalized Rule Journal\n\n", encoding="utf-8"
            )
        stamp = datetime.now().isoformat(timespec="seconds")
        with self.generalized_journal_path.open("a", encoding="utf-8") as file:
            file.write(f"- {stamp} {event}\n")

    def _generalized_rule_text(self, rule: GeneralizedRule) -> str:
        conditions = ", ".join(
            f"cell({condition.dx},{condition.dy})={condition.value}"
            for condition in rule.conditions
        )
        effects = ", ".join(
            f"set({effect.dx},{effect.dy})={effect.value}" for effect in rule.effects
        )
        return (
            f"{rule.action} anchored on {rule.anchor}: "
            f"IF {conditions or 'true'} THEN {effects or 'no change'}"
        )
