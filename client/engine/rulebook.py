from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from client.arc.types import GameAction
from client.engine.perception import EngineState
from client.engine.rule_schema import GeneralizedRule


class Rulebook:
    """Persistent logical rules used to simulate next states."""

    def __init__(self, base_path: str | Path, load_existing: bool = True) -> None:
        self.base_path = Path(base_path)
        self.json_path = self.base_path / "rules.json"
        self.generalized_rules: list[GeneralizedRule] = []
        self._next_id = 1
        if load_existing:
            self._load()
        if not self.json_path.exists():
            self._save()

    def add_generalized_rule(self, rule: GeneralizedRule) -> GeneralizedRule:
        prepared = rule if rule.id else rule.with_id(self._new_id())

        existing_by_id = self._find_by_id(prepared.id)
        if existing_by_id is not None:
            prepared = prepared.revised_from(existing_by_id)
            self._replace_rule(existing_by_id.id, prepared)
            self._save()
            return prepared

        equivalent = self._find_equivalent(prepared)
        if equivalent is not None:
            merged = self._merge_evidence(equivalent, prepared)
            if merged != equivalent:
                self._replace_rule(equivalent.id, merged)
                self._save()
            return merged

        self.generalized_rules.append(prepared)
        self._save()
        return prepared

    def add_generalized_rules(
        self, rules: list[GeneralizedRule]
    ) -> list[GeneralizedRule]:
        return [self.add_generalized_rule(rule) for rule in rules]

    def predict(self, before: EngineState, action: GameAction) -> list[EngineState]:
        predictions: list[EngineState] = []
        seen: set[EngineState] = set()
        for rule in self.generalized_rules:
            if rule.action != action.name:
                continue
            for predicted in rule.predict(before):
                if predicted in seen:
                    continue
                predictions.append(predicted)
                seen.add(predicted)
        return predictions

    def record_prediction_result(
        self,
        before: EngineState,
        action: GameAction,
        actual_after: EngineState,
        predictions: list[EngineState],
    ) -> None:
        if not predictions:
            return

        candidates = self._prediction_candidates(before, action)
        if not candidates:
            return

        if actual_after in predictions:
            changed = False
            for rule, predicted in candidates:
                if predicted != actual_after:
                    continue
                self._replace_rule(rule.id, rule.with_hit())
                changed = True
            if changed:
                self._save()
            return

        changed = False
        for rule, _predicted in candidates:
            self._replace_rule(
                rule.id,
                rule.with_contradiction(f"predicted wrong result for {action.name}"),
            )
            changed = True
        if changed:
            self._save()

    def known_rules_text(self) -> str:
        return "\n".join(
            f"- {rule.summary}"
            for rule in self.generalized_rules
            if rule.summary.strip()
        )

    def _prediction_candidates(
        self, before: EngineState, action: GameAction
    ) -> list[tuple[GeneralizedRule, EngineState]]:
        candidates: list[tuple[GeneralizedRule, EngineState]] = []
        for rule in self.generalized_rules:
            if rule.action != action.name:
                continue
            for predicted in rule.predict(before):
                candidates.append((rule, predicted))
        return candidates

    def _find_by_id(self, rule_id: str) -> GeneralizedRule | None:
        return next((rule for rule in self.generalized_rules if rule.id == rule_id), None)

    def _find_equivalent(self, candidate: GeneralizedRule) -> GeneralizedRule | None:
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

    def _replace_rule(self, rule_id: str, replacement: GeneralizedRule) -> None:
        for index, rule in enumerate(self.generalized_rules):
            if rule.id == rule_id:
                self.generalized_rules[index] = replacement
                return

    def _merge_evidence(
        self, existing: GeneralizedRule, incoming: GeneralizedRule
    ) -> GeneralizedRule:
        supports = tuple(dict.fromkeys([*existing.evidence_ids, *incoming.evidence_ids]))
        contradictions = tuple(
            dict.fromkeys([*existing.contradictions, *incoming.contradictions])
        )
        return replace(
            existing,
            evidence_ids=supports,
            contradictions=contradictions,
            prediction_hits=existing.prediction_hits + incoming.prediction_hits,
            prediction_failures=(
                existing.prediction_failures + incoming.prediction_failures
            ),
        )

    def _new_id(self) -> str:
        rule_id = f"G{self._next_id:06d}"
        self._next_id += 1
        return rule_id

    def _load(self) -> None:
        if not self.json_path.exists():
            return
        data = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.generalized_rules = [
            GeneralizedRule.from_data(item) for item in data.get("rules", [])
        ]
        self._next_id = int(
            data.get("next_id", len(self.generalized_rules) + 1)
        )

    def _save(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(
            json.dumps(
                {
                    "next_id": self._next_id,
                    "rules": [rule.to_data() for rule in self.generalized_rules],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
