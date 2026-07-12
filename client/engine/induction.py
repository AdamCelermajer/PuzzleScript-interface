from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from client.engine.memory import EngineMemory, TransitionRecord
from client.engine.rule_schema import candidate_rules_from_llm_json
from client.engine.rulebook import Rulebook
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

Offsets are relative to the anchor cell. Use only integer cell values from the boards.
""".strip()


@dataclass(frozen=True)
class NaturalRuleHypothesis:
    summary: str
    evidence_ids: tuple[str, ...]


def natural_rule_hypotheses_from_llm_json(
    data: dict,
) -> list[NaturalRuleHypothesis]:
    if not isinstance(data, dict):
        raise ValueError("LLM natural-rule response must be a JSON object")
    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("LLM natural-rule response field 'rules' must be a list")

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
            NaturalRuleHypothesis(summary=summary, evidence_ids=evidence_ids)
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
