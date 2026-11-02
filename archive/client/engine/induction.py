from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from client.engine.memory import EngineMemory, TransitionRecord
from client.engine.legend import format_legend
from client.engine.natural_rules import (
    NaturalRule,
    NaturalRuleLibrary,
    RuleFailureLog,
)
from client.engine.prompts import PromptStore
from client.engine.rule_schema import GeneralizedRule
from client.engine.rule_schema import candidate_rules_from_llm_json
from client.engine.rulebook import Rulebook
from client.engine.rule_attempts import RuleAttemptLog
from client.engine.verifier import RuleVerifier


RULE_FORMAT = """
Executable rule JSON shape:
  {
    "summary": "ACTION4 moves the player one cell right into empty space.",
    "action": "ACTION4",
    "anchor": {"value": 2},
    "conditions": [
      {"offset": [0, 0], "equals": 2},
      {"offset": [1, 0], "equals": 0}
    ],
    "effects": [
      {"offset": [0, 0], "set": 0},
      {"offset": [1, 0], "set": 2}
    ],
    "evidence_ids": ["T000001"]
  }

Offsets are [dx, dy] relative to the anchor cell:
- right is [1, 0]
- left is [-1, 0]
- down is [0, 1]
- up is [0, -1]
The first number never represents a row. Use only integer cell values from the boards.
""".strip()


@dataclass(frozen=True)
class NaturalRuleHypothesis:
    summary: str
    evidence_ids: tuple[str, ...]
    action: str = ""


def natural_rule_hypotheses_from_llm_json(
    data: dict,
) -> list[NaturalRuleHypothesis]:
    if not isinstance(data, dict):
        raise ValueError("LLM natural-rule response must be a JSON object")
    if "rule" in data:
        raw_rule = data.get("rule")
        raw_rules = [] if raw_rule is None else [raw_rule]
    else:
        raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("LLM natural-rule response field 'rules' must be a list")
    if len(raw_rules) > 1:
        raise ValueError("LLM natural-rule response must contain at most one rule")

    hypotheses: list[NaturalRuleHypothesis] = []
    for index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"natural rule {index} must be an object")
        summary = str(raw_rule.get("summary", "")).strip()
        if not summary:
            raise ValueError(
                f"natural rule {index} must include a natural-language summary"
            )
        raw_evidence = raw_rule.get("evidence_ids", [])
        if not isinstance(raw_evidence, list):
            raise ValueError(
                f"natural rule {index} field 'evidence_ids' must be a list"
            )
        evidence_ids = tuple(str(item) for item in raw_evidence if str(item).strip())
        if not evidence_ids:
            raise ValueError(f"natural rule {index} must cite at least one evidence id")
        hypotheses.append(
            NaturalRuleHypothesis(
                summary=summary,
                evidence_ids=evidence_ids,
                action=str(raw_rule.get("action", "")).strip().upper(),
            )
        )
    return hypotheses


class RuleInducer:
    """Hypothesizes rules in natural language, then compiles verified candidates."""

    def __init__(
        self,
        llm_client,
        library: Rulebook,
        verifier: RuleVerifier,
        event_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.library = library
        self.verifier = verifier
        self.event_sink = event_sink or (lambda _message: None)

    def propose_from_recent(
        self,
        game_name: str,
        records: list[TransitionRecord],
        image_data_urls: list[str] | None = None,
        events_text: str | None = None,
    ) -> list[str]:
        if not records:
            return []

        events = (
            events_text
            if events_text is not None
            else "\n\n".join(
                [
                    f"Event {index}:\n"
                    f"Action: {record.action.name}\n"
                    f"Board Before:\n{self._rows(record.before)}\n"
                    f"Board After:\n{self._rows(record.after)}"
                    for index, record in enumerate(records, start=1)
                ]
            )
        )
        known_rules_text = self.library.known_rules_text()
        sys_prompt, user_prompt = self._deduce_natural_rules_prompt(
            events,
            game_name=game_name,
            known_rules_text=known_rules_text,
        )
        try:
            natural_data = self._call_rule_model(
                sys_prompt,
                user_prompt,
                image_data_urls=image_data_urls,
                purpose="rule hypothesis",
            )
            hypotheses = natural_rule_hypotheses_from_llm_json(natural_data)
        except ValueError as e:
            self.event_sink(f"Rejected malformed natural rule hypothesis: {e}")
            return []

        if not hypotheses:
            return []

        sys_prompt, user_prompt = self._compile_rules_prompt(
            events,
            hypotheses,
            game_name=game_name,
        )
        try:
            data = self._call_rule_model(
                sys_prompt,
                user_prompt,
                image_data_urls=image_data_urls,
                purpose="rule schema",
            )
            candidates = candidate_rules_from_llm_json(data)
        except ValueError as e:
            self.event_sink(f"Rejected malformed rule candidate: {e}")
            return []

        results = [self.verifier.verify(rule) for rule in candidates]
        accepted = []
        for result in results:
            if result.accepted:
                accepted.append(result.rule)
                continue
            self.event_sink(
                "Rejected rule candidate: " + "; ".join(result.failures)
            )

        stored = self.library.add_generalized_rules(accepted)
        return [rule.id for rule in stored]

    def propose_from_memory(self, game_name: str, memory: EngineMemory) -> list[str]:
        events, images = memory.latest_visual_context()
        return self.propose_from_recent(
            game_name,
            memory.recent_transitions(1),
            image_data_urls=images,
            events_text=events or None,
        )

    def _call_rule_model(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "rule schema",
    ) -> dict:
        if hasattr(self.llm_client, "call_json"):
            return self.llm_client.call_json(
                system,
                prompt,
                image_data_urls=image_data_urls,
                purpose=purpose,
            )

        import json

        from client.engine.utils import extract_json

        response = self.llm_client._call(
            system,
            prompt,
            json_mode=True,
            image_data_urls=image_data_urls,
            purpose=purpose,
        )
        return json.loads(extract_json(response))

    def _flatten_rules(self, rules_by_category: object) -> list[str]:
        if not isinstance(rules_by_category, dict):
            return []
        flattened: list[str] = []
        for category, rules in rules_by_category.items():
            if not isinstance(rules, list):
                continue
            for rule in rules:
                text = str(rule).strip()
                if text:
                    flattened.append(f"{category}: {text}")
        return flattened

    def _rows(self, state) -> str:
        return "\n".join(state.rows())

    def _deduce_natural_rules_prompt(
        self,
        events: str,
        known_rules_text: str,
        game_name: str = "Unknown",
    ) -> tuple[str, str]:
        system = (
            "You infer puzzle mechanics in natural language. "
            f"You are observing a grid environment named '{game_name}'. "
            "You observe action/state transitions and describe only plain-language "
            "mechanical hypotheses.\n\n"
            "Only propose rules directly supported by the event log. "
            "Do not guess, do not duplicate known rules, and do not over-generalize from one direction. "
            "Do not output code, implementation details, or machine-checkable rule structures. "
            "Every hypothesis must cite the transition ids that support it.\n\n"
            'Output only JSON: {"rules": [{"summary": "one plain-language rule", '
            '"evidence_ids": ["T000001"]}]}\n'
            'If no rule is supported, output: {"rules": []}'
        )
        prompt = (
            "Known natural-language rules:\n"
            f"{known_rules_text}\n\n"
            f"Recent events:\n{events}\n\n"
            "Identify new or revised natural-language rules. Output only JSON."
        )
        return system, prompt

    def _compile_rules_prompt(
        self,
        events: str,
        hypotheses: list[NaturalRuleHypothesis],
        game_name: str = "Unknown",
    ) -> tuple[str, str]:
        hypothesis_text = "\n".join(
            f"- H{index}: {hypothesis.summary} "
            f"(evidence: {', '.join(hypothesis.evidence_ids)})"
            for index, hypothesis in enumerate(hypotheses, start=1)
        )
        system = (
            "You are a physics engine rule compiler. "
            f"You are observing a grid environment named '{game_name}'. "
            "Convert selected natural-language mechanic hypotheses into executable "
            "rule candidates that can be checked against the event log.\n\n"
            f"{RULE_FORMAT}\n\n"
            "Use only the provided hypotheses and the event log. "
            "Do not invent new mechanics during compilation. "
            "Every rule must keep a concise natural-language summary and cite the "
            "transition ids that support it.\n\n"
            'Output only JSON: {"rules": [<rule objects>]}\n'
            'If no hypothesis can be compiled, output: {"rules": []}'
        )
        prompt = (
            "Natural-language hypotheses:\n"
            f"{hypothesis_text}\n\n"
            f"Recent events:\n{events}\n\n"
            "Compile supported hypotheses into logical rules. Output only JSON."
        )
        return system, prompt


@dataclass(frozen=True)
class NaturalInductionResult:
    hypotheses: tuple[NaturalRuleHypothesis, ...] = ()
    failure_reason: str = ""

    @property
    def failed(self) -> bool:
        return bool(self.failure_reason)


@dataclass(frozen=True)
class LogicCompilationResult:
    logical_rule: GeneralizedRule | None = None
    failure_reason: str = ""
    raw_response: str = ""
    parsed_response: dict | None = None
    system_prompt: str = ""
    user_prompt: str = ""


class NaturalRuleInducer:
    """Produces plain-language hypotheses without exposing executable schemas."""

    def __init__(
        self, llm_client, prompt_store: PromptStore | None = None
    ) -> None:
        self.llm_client = llm_client
        self.prompt_store = prompt_store or PromptStore()

    def infer(
        self,
        transition: TransitionRecord,
        events: str,
        images: list[str],
        previous_rules: list[NaturalRule],
        game_name: str,
        legend: dict[int, str] | None = None,
    ) -> NaturalInductionResult:
        known = "\n".join(f"- {rule.summary}" for rule in previous_rules)
        system = (
            f"{self.prompt_store.get('natural_rule')}\n\n"
            f"You are observing a grid environment named '{game_name}'. "
            "Do not output executable schemas. "
            'Output only JSON: {"rule": {"action": "ACTION1", '
            '"summary": "...", "evidence_ids": ["T000001"]}}. '
            'Use {"rule": null} when no new mechanic is supported.'
        )
        prompt = (
            f"Legend:\n{format_legend(legend)}\n\n"
            f"Known natural-language rules:\n{known or '- none'}\n\n"
            f"Current transition id: {transition.id}\n"
            f"Executed action: {transition.action.name}\n\n"
            f"Evidence:\n{events}\n\n"
            "Infer at most one new natural-language mechanic. Output only JSON."
        )
        try:
            data = self.llm_client.call_json(
                system,
                prompt,
                image_data_urls=images,
                purpose="rule hypothesis",
            )
            hypotheses = natural_rule_hypotheses_from_llm_json(data)
            if hypotheses:
                hypothesis = hypotheses[0]
                if hypothesis.action != transition.action.name:
                    raise ValueError(
                        "natural rule action must match the executed action "
                        f"{transition.action.name}"
                    )
                if hypothesis.evidence_ids != (transition.id,):
                    raise ValueError(
                        "natural rule evidence must contain only the current "
                        f"transition {transition.id}"
                    )
        except (TypeError, ValueError) as exc:
            return NaturalInductionResult(failure_reason=str(exc))
        return NaturalInductionResult(hypotheses=tuple(hypotheses))


class LogicRuleCompiler:
    """Compiles one natural hypothesis into one executable rule candidate."""

    def __init__(
        self, llm_client, prompt_store: PromptStore | None = None
    ) -> None:
        self.llm_client = llm_client
        self.prompt_store = prompt_store or PromptStore()

    def compile_one(
        self,
        transition: TransitionRecord,
        hypothesis: NaturalRule,
        all_natural_rules: list[NaturalRule],
        logical_rules: list[GeneralizedRule],
        images: list[str],
        previous_failure: str = "",
        legend: dict[int, str] | None = None,
    ) -> LogicCompilationResult:
        natural_context = "\n".join(
            f"- {rule.id}: {rule.summary}" for rule in all_natural_rules
        )
        logical_context = "\n".join(
            f"- {rule.id}: {rule.summary}" for rule in logical_rules
        )
        retry_note = (
            f"\nPrevious attempt failed because: {previous_failure}\n"
            "Correct that specific failure in this attempt.\n"
            if previous_failure
            else ""
        )
        system = (
            f"{self.prompt_store.get('logic_compiler')}\n\n"
            f"{RULE_FORMAT}\n\n"
            'Output only JSON: {"rules": [<one rule object>]}. '
            'Use {"rules": []} if it cannot be compiled.'
        )
        prompt = (
            f"Hypothesis {hypothesis.id}: {hypothesis.summary}\n"
            f"Evidence ids: {', '.join(hypothesis.evidence_ids)}\n\n"
            f"Legend:\n{format_legend(legend)}\n\n"
            f"Transition:\n{transition.to_data()}\n\n"
            f"All natural rules:\n{natural_context or '- none'}\n\n"
            f"Verified logical rules:\n{logical_context or '- none'}\n"
            f"{retry_note}\nCompile the hypothesis. Output only JSON."
        )
        raw_response = ""
        parsed_response = None
        try:
            if hasattr(self.llm_client, "call_json_result"):
                response = self.llm_client.call_json_result(
                    system,
                    prompt,
                    image_data_urls=images,
                    purpose="rule schema",
                )
                raw_response = response.raw_response
                parsed_response = response.data
                if response.error:
                    return LogicCompilationResult(
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
                    purpose="rule schema",
                )
                parsed_response = data
                raw_response = json.dumps(data)
            candidates = candidate_rules_from_llm_json(data)
        except (TypeError, ValueError) as exc:
            return LogicCompilationResult(
                failure_reason=str(exc),
                raw_response=raw_response,
                parsed_response=parsed_response,
                system_prompt=system,
                user_prompt=prompt,
            )
        if not candidates:
            return LogicCompilationResult(
                failure_reason="compiler returned no logical rule",
                raw_response=raw_response,
                parsed_response=parsed_response,
                system_prompt=system,
                user_prompt=prompt,
            )
        if len(candidates) != 1:
            return LogicCompilationResult(
                failure_reason="compiler must return exactly one logical rule",
                raw_response=raw_response,
                parsed_response=parsed_response,
                system_prompt=system,
                user_prompt=prompt,
            )
        return LogicCompilationResult(
            logical_rule=candidates[0],
            raw_response=raw_response,
            parsed_response=parsed_response,
            system_prompt=system,
            user_prompt=prompt,
        )


class RuleLearner:
    """Persists natural hypotheses and admits only verified logical rules."""

    def __init__(
        self,
        natural_rule_inducer: NaturalRuleInducer,
        natural_rule_library: NaturalRuleLibrary,
        logic_rule_compiler: LogicRuleCompiler,
        logical_rulebook: Rulebook,
        verifier: RuleVerifier,
        failure_log: RuleFailureLog,
        rule_attempt_log: RuleAttemptLog | None = None,
        rule_reviser=None,
        max_logic_attempts: int = 3,
        allowed_exhausted_hypotheses: int = 3,
        event_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.natural_rule_inducer = natural_rule_inducer
        self.natural_rule_library = natural_rule_library
        self.logic_rule_compiler = logic_rule_compiler
        self.logical_rulebook = logical_rulebook
        self.verifier = verifier
        self.failure_log = failure_log
        self.rule_attempt_log = rule_attempt_log
        self.rule_reviser = rule_reviser
        self.max_logic_attempts = max(1, int(max_logic_attempts))
        self.allowed_exhausted_hypotheses = max(
            0, int(allowed_exhausted_hypotheses)
        )
        self.exhausted_hypothesis_count = 0
        self.event_sink = event_sink or (lambda _message: None)

    def learn_from_memory(
        self,
        game_name: str,
        memory: EngineMemory,
        should_stop: Callable[[], bool] | None = None,
        legend: dict[int, str] | None = None,
    ) -> str:
        records = memory.recent_transitions(1)
        if not records:
            return "no_transition"
        if should_stop and should_stop():
            return "cancelled"
        transition = records[0]
        events, images = memory.latest_visual_context()
        infer_args = (
            transition,
            events,
            images,
            self.natural_rule_library.active(),
            game_name,
        )
        result = (
            self.natural_rule_inducer.infer(*infer_args, legend=legend)
            if legend is not None
            else self.natural_rule_inducer.infer(*infer_args)
        )
        if result.failed:
            self.failure_log.append(
                "natural_induction",
                result.failure_reason,
                transition_id=transition.id,
            )
            self.event_sink(
                f"Natural-rule induction failed: {result.failure_reason}"
            )
            return "learning_failed"

        if not result.hypotheses:
            return "no_new_rules"
        candidate = result.hypotheses[0]
        hypothesis = NaturalRule(
            id=f"C-{transition.id}",
            summary=candidate.summary,
            evidence_ids=candidate.evidence_ids,
            action=candidate.action,
            status="candidate",
        )
        self.event_sink(
            f"Candidate natural rule for {transition.id}: {hypothesis.summary}"
        )
        rule, failure = self.compile_and_verify(
            hypothesis,
            transition,
            images,
            memory,
            should_stop=should_stop,
            legend=legend,
        )
        if rule is not None:
            stored = self.logical_rulebook.add_generalized_rule(rule)
            natural_rule, created = self.natural_rule_library.promote(
                hypothesis, stored
            )
            self.exhausted_hypothesis_count = 0
            if created:
                self.event_sink(
                    f"Verified natural rule {natural_rule.id}: "
                    f"{natural_rule.summary}"
                )
            else:
                self.event_sink(
                    f"Reused natural rule {natural_rule.id}; "
                    f"added evidence {transition.id}"
                )
            self.event_sink(
                f"Verified logical rule {stored.id}: {stored.summary}"
            )
            return "learning_complete"
        if failure == "cancelled":
            return "cancelled"
        self.exhausted_hypothesis_count += 1
        self.event_sink(
            f"Rejected natural-rule candidate for {transition.id}: {failure}"
        )
        if (
            self.exhausted_hypothesis_count
            > self.allowed_exhausted_hypotheses
        ):
            self.failure_log.append(
                "process_stopped",
                "repeated_rule_learning_failure",
                exhausted_hypotheses=self.exhausted_hypothesis_count,
            )
            return "stop_required"
        return "learning_complete"

    def revise_from_memory(
        self,
        contradicted_rule_ids: list[str] | tuple[str, ...],
        memory: EngineMemory,
        should_stop: Callable[[], bool] | None = None,
        legend: dict[int, str] | None = None,
    ) -> str:
        records = memory.recent_transitions(1)
        if not records:
            return "no_transition"
        transition = records[0]
        old_rules = self.logical_rulebook.rules_by_id(contradicted_rule_ids)
        if not old_rules or self.rule_reviser is None:
            self.failure_log.append(
                "rule_revision",
                "revision unavailable for contradicted rules",
                transition_id=transition.id,
                logical_rule_ids=list(contradicted_rule_ids),
            )
            return "revision_failed"

        linked_natural_rules = self.natural_rule_library.mark_contradicted(
            contradicted_rule_ids, transition.id
        )
        _events, images = memory.latest_visual_context()
        previous_failure = ""
        for attempt in range(1, self.max_logic_attempts + 1):
            if should_stop and should_stop():
                return "cancelled"
            revision = self.rule_reviser.revise(
                old_rules,
                linked_natural_rules,
                transition,
                images,
                previous_failure,
                legend=legend,
            )
            verification = None
            if revision.logical_rules:
                verification = self.verifier.verify_revision(
                    revision.logical_rules, old_rules, transition
                )
                if verification.accepted:
                    self._record_revision_attempt(
                        contradicted_rule_ids,
                        transition,
                        attempt,
                        revision,
                        verification,
                        "accepted",
                    )
                    stored = self.logical_rulebook.commit_revision(
                        contradicted_rule_ids, list(revision.logical_rules)
                    )
                    replacements = self.natural_rule_library.commit_revision(
                        linked_natural_rules, stored
                    )
                    self.exhausted_hypothesis_count = 0
                    self.event_sink(
                        "Revised rules "
                        + ", ".join(contradicted_rule_ids)
                        + " -> "
                        + ", ".join(rule.id for rule in stored)
                    )
                    if replacements:
                        self.event_sink(
                            "Revised natural rules: "
                            + ", ".join(rule.id for rule in replacements)
                        )
                    return "revision_complete"
                previous_failure = "; ".join(verification.failures)
                if verification.diagnostics:
                    previous_failure += "; diagnostics: " + json.dumps(
                        verification.diagnostics,
                        separators=(",", ":"),
                    )
            else:
                previous_failure = revision.failure_reason or "rule revision failed"
            self._record_revision_attempt(
                contradicted_rule_ids,
                transition,
                attempt,
                revision,
                verification,
                "rejected",
            )
            self.failure_log.append(
                "rule_revision",
                previous_failure,
                transition_id=transition.id,
                logical_rule_ids=list(contradicted_rule_ids),
                attempt=attempt,
            )
            self.event_sink(
                f"Rule revision attempt {attempt}/{self.max_logic_attempts} failed: "
                f"{previous_failure}"
            )
        return "revision_failed"

    def compile_and_verify(
        self,
        hypothesis: NaturalRule,
        transition: TransitionRecord,
        images: list[str],
        memory: EngineMemory,
        should_stop: Callable[[], bool] | None = None,
        legend: dict[int, str] | None = None,
    ) -> tuple[GeneralizedRule | None, str]:
        previous_failure = ""
        for attempt in range(1, self.max_logic_attempts + 1):
            if should_stop and should_stop():
                return None, "cancelled"
            compile_args = (
                transition,
                hypothesis,
                self.natural_rule_library.active(),
                self.logical_rulebook.active_rules(),
                images,
                previous_failure,
            )
            compilation = (
                self.logic_rule_compiler.compile_one(*compile_args, legend=legend)
                if legend is not None
                else self.logic_rule_compiler.compile_one(*compile_args)
            )
            candidate = compilation.logical_rule
            verification = None
            if candidate is None:
                previous_failure = (
                    compilation.failure_reason or "logical compilation failed"
                )
            else:
                verification = self.verifier.verify(candidate)
                if verification.accepted:
                    self._record_attempt(
                        hypothesis,
                        transition,
                        attempt,
                        compilation,
                        verification,
                        "accepted",
                    )
                    return candidate, ""
                previous_failure = "; ".join(verification.failures)
                if verification.diagnostics:
                    previous_failure += "; diagnostics: " + json.dumps(
                        verification.diagnostics,
                        separators=(",", ":"),
                    )
            self._record_attempt(
                hypothesis,
                transition,
                attempt,
                compilation,
                verification,
                "rejected",
            )
            self.failure_log.append(
                "logic_compile_verify",
                previous_failure,
                hypothesis_id=hypothesis.id,
                transition_id=transition.id,
                attempt=attempt,
            )
            self.event_sink(
                f"Rule {hypothesis.id} attempt {attempt}/{self.max_logic_attempts} "
                f"failed: {previous_failure}"
            )
        return None, previous_failure

    def _record_attempt(
        self,
        hypothesis: NaturalRule,
        transition: TransitionRecord,
        attempt: int,
        compilation: LogicCompilationResult,
        verification,
        outcome: str,
    ) -> None:
        if self.rule_attempt_log is None:
            return
        model = getattr(
            getattr(self.logic_rule_compiler.llm_client, "cfg", None),
            "model",
            "",
        )
        self.rule_attempt_log.append(
            stage="compile",
            hypothesis_id=hypothesis.id,
            transition_id=transition.id,
            attempt=attempt,
            model=model,
            system_prompt=compilation.system_prompt,
            user_prompt=compilation.user_prompt,
            raw_response=compilation.raw_response,
            parsed_response=compilation.parsed_response,
            candidate=(
                compilation.logical_rule.to_data()
                if compilation.logical_rule is not None
                else None
            ),
            compilation_failure=compilation.failure_reason,
            verification=(
                {
                    "accepted": verification.accepted,
                    "failures": list(verification.failures),
                    "diagnostics": list(verification.diagnostics),
                }
                if verification is not None
                else None
            ),
            outcome=outcome,
        )

    def _record_revision_attempt(
        self,
        contradicted_rule_ids,
        transition,
        attempt,
        revision,
        verification,
        outcome,
    ) -> None:
        if self.rule_attempt_log is None:
            return
        model = getattr(
            getattr(self.rule_reviser.llm_client, "cfg", None), "model", ""
        )
        self.rule_attempt_log.append(
            stage="revision",
            logical_rule_ids=list(contradicted_rule_ids),
            transition_id=transition.id,
            attempt=attempt,
            model=model,
            system_prompt=revision.system_prompt,
            user_prompt=revision.user_prompt,
            raw_response=revision.raw_response,
            parsed_response=revision.parsed_response,
            candidates=[rule.to_data() for rule in revision.logical_rules],
            compilation_failure=revision.failure_reason,
            verification=(
                {
                    "accepted": verification.accepted,
                    "failures": list(verification.failures),
                    "diagnostics": list(verification.diagnostics),
                }
                if verification is not None
                else None
            ),
            outcome=outcome,
        )
