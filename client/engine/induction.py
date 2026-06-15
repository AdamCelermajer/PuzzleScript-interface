from __future__ import annotations

from typing import Callable

from client.engine import prompts
from client.engine.history import TransitionRecord
from client.engine.rule_schema import candidate_rules_from_llm_json
from client.engine.rules import RuleLibrary
from client.engine.verifier import RuleVerifier
from client.engine.visual_context import VisualTransition


class RuleInducer:
    """Asks the LLM for hypotheses, then stores them as non-executable text."""

    def __init__(
        self,
        llm_client,
        library: RuleLibrary,
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
        visual_transition: VisualTransition | None = None,
    ) -> list[str]:
        if not records:
            return []

        events = (
            visual_transition.prompt_text()
            if visual_transition is not None
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
        image_data_urls = (
            visual_transition.image_data_urls()
            if visual_transition is not None
            else []
        )
        sys_prompt, user_prompt = prompts.get_deduce_rules_prompt(
            events,
            self.library.known_rules_text(),
            "",
            game_name=game_name,
        )
        try:
            data = self._call_rule_model(
                sys_prompt,
                user_prompt,
                image_data_urls=image_data_urls,
            )
            candidates = candidate_rules_from_llm_json(data)
        except ValueError as e:
            self.event_sink(f"Rejected malformed rule candidate: {e}")
            return []

        verified = [self.verifier.verify(rule) for rule in candidates]
        stored = self.library.add_generalized_rules(verified)
        return [rule.id for rule in stored if rule.status == "verified"]

    def _call_rule_model(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
    ) -> dict:
        if hasattr(self.llm_client, "call_json"):
            return self.llm_client.call_json(
                system,
                prompt,
                model_type="pro",
                image_data_urls=image_data_urls,
            )

        import json
        import inspect

        from client.engine.utils import extract_json

        call = self.llm_client._call
        try:
            signature = inspect.signature(call)
        except (TypeError, ValueError):
            signature = None
        kwargs = {"model_type": "pro", "json_mode": True}
        if signature is None or "image_data_urls" in signature.parameters:
            kwargs["image_data_urls"] = image_data_urls
        response = self.llm_client._call(
            system,
            prompt,
            **kwargs,
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
