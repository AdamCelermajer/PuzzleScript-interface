from __future__ import annotations

from dataclasses import dataclass

from client.engine.memory import EngineMemory, TransitionRecord
from client.engine.rule_schema import GeneralizedRule


@dataclass(frozen=True)
class VerificationResult:
    rule: GeneralizedRule
    failures: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return not self.failures


class RuleVerifier:
    """Verifies executable candidate rules against transition evidence."""

    def __init__(self, memory: EngineMemory) -> None:
        self.memory = memory

    def verify(self, rule: GeneralizedRule) -> VerificationResult:
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

        return VerificationResult(rule=rule, failures=tuple(failures))

    def _record_by_id(self, record_id: str) -> TransitionRecord | None:
        return self.memory.transition_by_id(record_id)
