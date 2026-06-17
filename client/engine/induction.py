from __future__ import annotations

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


class RuleInducer:
    """Asks the LLM for executable logical rules, then stores their evidence."""

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
        sys_prompt, user_prompt = self._deduce_rules_prompt(
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

        checked = [self.verifier.verify(rule) for rule in candidates]
        stored = self.library.add_generalized_rules(checked)
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
    ) -> dict:
        if hasattr(self.llm_client, "call_json"):
            return self.llm_client.call_json(
                system,
                prompt,
                image_data_urls=image_data_urls,
                purpose="rule creation",
            )

        import json

        from client.engine.utils import extract_json

        response = self.llm_client._call(
            system,
            prompt,
            json_mode=True,
            image_data_urls=image_data_urls,
            purpose="rule creation",
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

    def _deduce_rules_prompt(
        self,
        events: str,
        known_rules_text: str,
        focus_prompt: str,
        game_name: str = "Unknown",
    ) -> tuple[str, str]:
        system = (
            "You are a physics engine reverse-engineer. "
            f"You are observing a grid environment named '{game_name}'. "
            "You observe action/state transitions and propose executable mechanical rules.\n\n"
            f"{RULE_FORMAT}\n\n"
            "Only propose rules directly supported by the event log. "
            "Do not guess, do not duplicate known rules, and do not over-generalize from one direction. "
            "Every rule must include a concise natural-language summary and cite the "
            "transition ids that support it.\n\n"
            'Output only JSON: {"rules": [<rule objects>]}\n'
            'If no rule is supported, output: {"rules": []}'
        )
        prompt = (
            f"{known_rules_text}\n\n"
            f"Recent events:\n{events}\n\n"
            f"{focus_prompt}"
            "Identify new or revised logical rules. Output only JSON."
        )
        return system, prompt
