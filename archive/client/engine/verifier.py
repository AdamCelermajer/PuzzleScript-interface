from __future__ import annotations

from dataclasses import dataclass

from client.engine.memory import EngineMemory, TransitionRecord
from client.engine.rule_schema import GeneralizedRule


@dataclass(frozen=True)
class VerificationResult:
    rule: GeneralizedRule
    failures: tuple[str, ...] = ()
    diagnostics: tuple[dict, ...] = ()

    @property
    def accepted(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class RevisionVerificationResult:
    rules: tuple[GeneralizedRule, ...]
    failures: tuple[str, ...] = ()
    diagnostics: tuple[dict, ...] = ()

    @property
    def accepted(self) -> bool:
        return not self.failures


class RuleVerifier:
    """Verifies executable candidate rules against transition evidence."""

    def __init__(self, memory: EngineMemory) -> None:
        self.memory = memory

    def verify(self, rule: GeneralizedRule) -> VerificationResult:
        failures: list[str] = []
        diagnostics: list[dict] = []
        for evidence_id in rule.evidence_ids:
            record = self._record_by_id(evidence_id)
            if record is None:
                failures.append(f"{evidence_id}: evidence not found")
                diagnostics.append(
                    {"evidence_id": evidence_id, "type": "evidence_not_found"}
                )
                continue
            if record.action.name != rule.action:
                failures.append(
                    f"{evidence_id}: action mismatch "
                    f"expected {rule.action}, got {record.action.name}"
                )
                diagnostics.append(
                    {
                        "evidence_id": evidence_id,
                        "type": "action_mismatch",
                        "expected": rule.action,
                        "observed": record.action.name,
                    }
                )
                continue
            predictions = rule.predict(record.before)
            if record.after not in predictions:
                failures.append(f"{evidence_id}: predicted states did not include after")
                closest = None
                if predictions:
                    closest_state = min(
                        predictions,
                        key=lambda prediction: len(prediction.changed_cells(record.after)),
                    )
                    closest = list(closest_state.changed_cells(record.after))
                diagnostics.append(
                    {
                        "evidence_id": evidence_id,
                        "type": "prediction_mismatch",
                        "prediction_count": len(predictions),
                        "closest_cell_differences": closest,
                    }
                )

        return VerificationResult(
            rule=rule,
            failures=tuple(failures),
            diagnostics=tuple(diagnostics),
        )

    def verify_revision(
        self,
        rules: list[GeneralizedRule] | tuple[GeneralizedRule, ...],
        contradicted_rules: list[GeneralizedRule],
        contradiction: TransitionRecord,
    ) -> RevisionVerificationResult:
        failures: list[str] = []
        diagnostics: list[dict] = []
        allowed_ids = set(
            [
                contradiction.id,
                *[
                    evidence_id
                    for rule in contradicted_rules
                    for evidence_id in rule.evidence_ids
                ],
            ]
        )
        expected_action = contradiction.action.name
        for index, rule in enumerate(rules, start=1):
            if rule.action != expected_action:
                failures.append(
                    f"revision rule {index}: action must remain {expected_action}"
                )
            unknown_ids = set(rule.evidence_ids) - allowed_ids
            if unknown_ids:
                failures.append(
                    f"revision rule {index}: unsupported evidence ids "
                    + ", ".join(sorted(unknown_ids))
                )
            result = self.verify(rule)
            failures.extend(
                f"revision rule {index}: {failure}" for failure in result.failures
            )
            diagnostics.extend(result.diagnostics)

        required_ids = list(
            dict.fromkeys(
                [
                    *[
                        evidence_id
                        for rule in contradicted_rules
                        for evidence_id in rule.evidence_ids
                    ],
                    contradiction.id,
                ]
            )
        )
        for evidence_id in required_ids:
            record = self._record_by_id(evidence_id)
            if record is None:
                failures.append(f"{evidence_id}: evidence not found")
                continue
            covered = False
            for index, rule in enumerate(rules, start=1):
                predictions = rule.predict(record.before)
                if predictions and record.after not in predictions:
                    failures.append(
                        f"revision rule {index}: {evidence_id} still predicts a wrong result"
                    )
                    diagnostics.append(
                        {
                            "evidence_id": evidence_id,
                            "type": "revision_prediction_mismatch",
                            "rule_index": index,
                        }
                    )
                if record.after in predictions:
                    covered = True
            if not covered:
                failures.append(f"{evidence_id}: revised rules do not cover observed result")

        return RevisionVerificationResult(
            rules=tuple(rules),
            failures=tuple(dict.fromkeys(failures)),
            diagnostics=tuple(diagnostics),
        )

    def _record_by_id(self, record_id: str) -> TransitionRecord | None:
        return self.memory.transition_by_id(record_id)
