from __future__ import annotations

from client.engine.history import TransitionHistory, TransitionRecord
from client.engine.rule_schema import GeneralizedRule


class RuleVerifier:
    """Verifies executable candidate rules against transition evidence."""

    def __init__(self, history: TransitionHistory) -> None:
        self.history = history

    def verify(self, rule: GeneralizedRule) -> GeneralizedRule:
        failures: list[str] = []
        for evidence_id in rule.evidence_ids:
            record = self._record_by_id(evidence_id)
            if record is None:
                failures.append(f"{evidence_id}: evidence not found")
                continue
            if record.action.name != rule.action:
                failures.append(
                    f"{evidence_id}: action mismatch "
                    f"expected {rule.action}, got {record.action.name}"
                )
                continue
            predictions = rule.predict(record.before)
            if record.after not in predictions:
                failures.append(f"{evidence_id}: predicted states did not include after")

        if failures:
            return rule.rejected(tuple(failures))
        return rule.verified()

    def _record_by_id(self, record_id: str) -> TransitionRecord | None:
        for record in self.history.all():
            if record.id == record_id:
                return record
        return None
