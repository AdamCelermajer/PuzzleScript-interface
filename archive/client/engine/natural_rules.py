from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NaturalRule:
    id: str
    summary: str
    evidence_ids: tuple[str, ...]
    action: str = ""
    status: str = "pending"
    logical_rule_id: str = ""
    failure_reason: str = ""
    lifecycle: str = "active"
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "NaturalRule":
        status = str(data.get("status", "pending"))
        return cls(
            id=str(data["id"]),
            summary=str(data["summary"]),
            evidence_ids=tuple(str(item) for item in data.get("evidence_ids", [])),
            action=str(data.get("action", "")),
            status=status,
            logical_rule_id=str(data.get("logical_rule_id", "")),
            failure_reason=str(data.get("failure_reason", "")),
            lifecycle=str(
                data.get("lifecycle", "archived" if status == "archived" else "active")
            ),
            supersedes=tuple(str(item) for item in data.get("supersedes", [])),
            superseded_by=tuple(
                str(item) for item in data.get("superseded_by", [])
            ),
        )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "evidence_ids": list(self.evidence_ids),
            "action": self.action,
            "status": self.status,
            "logical_rule_id": self.logical_rule_id,
            "failure_reason": self.failure_reason,
            "lifecycle": self.lifecycle,
            "supersedes": list(self.supersedes),
            "superseded_by": list(self.superseded_by),
        }


class NaturalRuleLibrary:
    """Persistent natural-language hypotheses kept separate from logical rules."""

    def __init__(self, path: str | Path, load_existing: bool = True) -> None:
        self.path = Path(path)
        self.rules: list[NaturalRule] = []
        self._next_id = 1
        if load_existing:
            self._load()
        if not self.path.exists():
            self._save()

    def all(self) -> list[NaturalRule]:
        return list(self.rules)

    def active(self) -> list[NaturalRule]:
        return [
            rule
            for rule in self.rules
            if rule.lifecycle == "active" and rule.status != "archived"
        ]

    def known_rules_text(self) -> str:
        return "\n".join(f"- {rule.summary}" for rule in self.active())

    def merge(self, hypotheses: list[object]) -> list[NaturalRule]:
        updates: list[NaturalRule] = []
        for hypothesis in hypotheses:
            summary = str(getattr(hypothesis, "summary", "")).strip()
            evidence_ids = tuple(
                str(item) for item in getattr(hypothesis, "evidence_ids", ())
            )
            action = str(getattr(hypothesis, "action", "")).strip().upper()
            if not summary or not evidence_ids:
                continue
            existing = next(
                (rule for rule in self.rules if rule.summary.casefold() == summary.casefold()),
                None,
            )
            if existing is not None:
                merged_ids = tuple(dict.fromkeys([*existing.evidence_ids, *evidence_ids]))
                if merged_ids != existing.evidence_ids:
                    self._replace(existing.id, replace(existing, evidence_ids=merged_ids))
                    self._save()
                continue
            rule = NaturalRule(
                id=f"N{self._next_id:06d}",
                summary=summary,
                evidence_ids=evidence_ids,
                action=action,
            )
            self._next_id += 1
            self.rules.append(rule)
            updates.append(rule)
        if updates:
            self._save()
        return updates

    def promote(
        self, hypothesis: object, logical_rule: object
    ) -> tuple[NaturalRule, bool]:
        """Promote a verified candidate or merge evidence into its canonical NL rule."""
        logical_rule_id = str(getattr(logical_rule, "id", ""))
        evidence_ids = tuple(
            dict.fromkeys(
                [
                    *getattr(hypothesis, "evidence_ids", ()),
                    *getattr(logical_rule, "evidence_ids", ()),
                ]
            )
        )
        existing = next(
            (
                rule
                for rule in self.rules
                if rule.logical_rule_id == logical_rule_id
                and rule.lifecycle == "active"
            ),
            None,
        )
        if existing is not None:
            merged = replace(
                existing,
                evidence_ids=tuple(
                    dict.fromkeys([*existing.evidence_ids, *evidence_ids])
                ),
            )
            if merged != existing:
                self._replace(existing.id, merged)
                self._save()
            return merged, False

        rule = NaturalRule(
            id=f"N{self._next_id:06d}",
            summary=str(getattr(logical_rule, "summary", "")).strip()
            or str(getattr(hypothesis, "summary", "")).strip(),
            evidence_ids=evidence_ids,
            action=str(getattr(logical_rule, "action", "")).strip().upper()
            or str(getattr(hypothesis, "action", "")).strip().upper(),
            status="compiled",
            logical_rule_id=logical_rule_id,
        )
        self._next_id += 1
        self.rules.append(rule)
        self._save()
        return rule, True

    def mark_compiled(self, hypothesis: NaturalRule, logical_rule: object) -> None:
        self._replace(
            hypothesis.id,
            replace(
                hypothesis,
                status="compiled",
                logical_rule_id=str(getattr(logical_rule, "id", "")),
                failure_reason="",
            ),
        )
        self._save()

    def archive(self, hypothesis: NaturalRule, failure_reason: str) -> None:
        self._replace(
            hypothesis.id,
            replace(
                hypothesis,
                status="archived",
                failure_reason=str(failure_reason),
                lifecycle="archived",
            ),
        )
        self._save()

    def linked_to(
        self, logical_rule_ids: list[str] | tuple[str, ...]
    ) -> list[NaturalRule]:
        wanted = set(logical_rule_ids)
        return [
            rule
            for rule in self.rules
            if rule.logical_rule_id in wanted and rule.lifecycle == "active"
        ]

    def mark_contradicted(
        self,
        logical_rule_ids: list[str] | tuple[str, ...],
        transition_id: str,
    ) -> list[NaturalRule]:
        linked = self.linked_to(logical_rule_ids)
        for rule in linked:
            self._replace(
                rule.id,
                replace(
                    rule,
                    lifecycle="contradicted",
                    failure_reason=f"contradicted by {transition_id}",
                ),
            )
        if linked:
            self._save()
        return linked

    def commit_revision(
        self,
        contradicted_rules: list[NaturalRule],
        logical_rules: list[object],
    ) -> list[NaturalRule]:
        old_ids = tuple(rule.id for rule in contradicted_rules)
        created: list[NaturalRule] = []
        for logical_rule in logical_rules:
            rule = NaturalRule(
                id=f"N{self._next_id:06d}",
                summary=str(getattr(logical_rule, "summary", "")),
                evidence_ids=tuple(getattr(logical_rule, "evidence_ids", ())),
                action=str(getattr(logical_rule, "action", "")),
                status="compiled",
                logical_rule_id=str(getattr(logical_rule, "id", "")),
                lifecycle="active",
                supersedes=old_ids,
            )
            self._next_id += 1
            created.append(rule)
        new_ids = tuple(rule.id for rule in created)
        for old in contradicted_rules:
            current = next((rule for rule in self.rules if rule.id == old.id), old)
            self._replace(
                old.id,
                replace(current, lifecycle="superseded", superseded_by=new_ids),
            )
        self.rules.extend(created)
        self._save()
        return created

    def _replace(self, rule_id: str, replacement: NaturalRule) -> None:
        for index, rule in enumerate(self.rules):
            if rule.id == rule_id:
                self.rules[index] = replacement
                return

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.rules = [NaturalRule.from_data(item) for item in data.get("rules", [])]
        self._next_id = int(data.get("next_id", len(self.rules) + 1))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "next_id": self._next_id,
                    "rules": [rule.to_data() for rule in self.rules],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


class RuleFailureLog:
    """Append-only compact record of rule-learning failures."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, stage: str, reason: str, **context: object) -> dict[str, Any]:
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": str(stage),
            "reason": str(reason),
        }
        record.update(
            {
                key: value
                for key, value in context.items()
                if value is not None and value != ""
            }
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        return record

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows[-max(0, int(limit)) :]
