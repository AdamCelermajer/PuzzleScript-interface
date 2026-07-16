from __future__ import annotations

import json
from dataclasses import dataclass

from client.engine.induction import RULE_FORMAT
from client.engine.legend import format_legend
from client.engine.memory import TransitionRecord
from client.engine.natural_rules import NaturalRule
from client.engine.prompts import PromptStore
from client.engine.rule_schema import GeneralizedRule, candidate_rules_from_llm_json


@dataclass(frozen=True)
class RevisionCompilationResult:
    logical_rules: tuple[GeneralizedRule, ...] = ()
    failure_reason: str = ""
    raw_response: str = ""
    parsed_response: dict | None = None
    system_prompt: str = ""
    user_prompt: str = ""


class RuleReviser:
    """Revises contradicted natural and logical rules as one versioned unit."""

    def __init__(
        self, llm_client, prompt_store: PromptStore | None = None
    ) -> None:
        self.llm_client = llm_client
        self.prompt_store = prompt_store or PromptStore()

    def revise(
        self,
        contradicted_logical_rules: list[GeneralizedRule],
        linked_natural_rules: list[NaturalRule],
        transition: TransitionRecord,
        images: list[str],
        previous_failure: str = "",
        legend: dict[int, str] | None = None,
    ) -> RevisionCompilationResult:
        old_evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for rule in contradicted_logical_rules
                for evidence_id in rule.evidence_ids
            )
        )
        allowed_evidence_ids = tuple(
            dict.fromkeys([*old_evidence_ids, transition.id])
        )
        retry_note = (
            f"\nPrevious revision failed because: {previous_failure}\n"
            "Correct that specific failure in this attempt.\n"
            if previous_failure
            else ""
        )
        system = (
            f"{self.prompt_store.get('rule_revision')}\n\n"
            "Each returned executable rule also supplies the replacement "
            "natural-language summary.\n\n"
            f"{RULE_FORMAT}\n\n"
            "A corrected old-case rule may cite old supporting transitions. A new-case "
            "rule must cite the contradicting transition. Use only the allowed evidence "
            "ids. Output only JSON: {\"rules\": [<one or two rule objects>]} ."
        )
        logical_context = json.dumps(
            [rule.to_data() for rule in contradicted_logical_rules], indent=2
        )
        natural_context = json.dumps(
            [rule.to_data() for rule in linked_natural_rules], indent=2
        )
        prompt = (
            f"Legend:\n{format_legend(legend)}\n\n"
            f"Contradicted logical rules:\n{logical_context}\n\n"
            f"Linked natural rules:\n{natural_context}\n\n"
            f"Old positive evidence ids: {', '.join(old_evidence_ids) or 'none'}\n"
            f"Contradicting transition:\n{json.dumps(transition.to_data(), indent=2)}\n\n"
            f"Allowed evidence ids: {', '.join(allowed_evidence_ids)}\n"
            f"Cell differences: {transition.before.changed_cells(transition.after)}\n"
            f"{retry_note}\nRevise the mechanic. Output only JSON."
        )
        raw_response = ""
        parsed_response = None
        try:
            if hasattr(self.llm_client, "call_json_result"):
                response = self.llm_client.call_json_result(
                    system,
                    prompt,
                    image_data_urls=images,
                    purpose="rule revision",
                )
                raw_response = response.raw_response
                parsed_response = response.data
                if response.error:
                    return RevisionCompilationResult(
                        failure_reason=response.error,
                        raw_response=raw_response,
                        parsed_response=parsed_response,
                        system_prompt=system,
                        user_prompt=prompt,
                    )
                data = response.data or {}
            else:
                data = self.llm_client.call_json(
                    system,
                    prompt,
                    image_data_urls=images,
                    purpose="rule revision",
                )
                parsed_response = data
                raw_response = json.dumps(data)
            candidates = candidate_rules_from_llm_json(data)
        except (TypeError, ValueError) as exc:
            return RevisionCompilationResult(
                failure_reason=str(exc),
                raw_response=raw_response,
                parsed_response=parsed_response,
                system_prompt=system,
                user_prompt=prompt,
            )
        if not 1 <= len(candidates) <= 2:
            return RevisionCompilationResult(
                failure_reason="reviser must return one or two logical rules",
                raw_response=raw_response,
                parsed_response=parsed_response,
                system_prompt=system,
                user_prompt=prompt,
            )
        return RevisionCompilationResult(
            logical_rules=tuple(rule.with_id("") for rule in candidates),
            raw_response=raw_response,
            parsed_response=parsed_response,
            system_prompt=system,
            user_prompt=prompt,
        )
