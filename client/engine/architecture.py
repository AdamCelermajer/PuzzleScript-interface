from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from client.engine.history import TransitionHistory
from client.engine.induction import RuleInducer
from client.engine.llm_client import Config
from client.engine.memory import EngineMemory
from client.engine.perception import Perception
from client.engine.planning import RuleFirstPlanner
from client.engine.rulebook import EngineRulebook
from client.engine.rules import RuleLibrary
from client.engine.verifier import RuleVerifier


def game_rules_path(rules_dir: str | Path, game_id: str) -> Path:
    safe_name = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in game_id
    )
    return Path(rules_dir) / safe_name


@dataclass
class EngineArchitecture:
    perceiver: Perception
    history: TransitionHistory
    library: RuleLibrary
    memory: EngineMemory
    rulebook: EngineRulebook
    inducer: RuleInducer
    planner: RuleFirstPlanner
    base_path: Path

    @classmethod
    def from_config(
        cls, config: Config, llm_client, event_sink=None
    ) -> "EngineArchitecture":
        base_path = game_rules_path(config.rules_dir, config.game)
        history = TransitionHistory(base_path / "transitions.jsonl")
        library = RuleLibrary(base_path)
        memory = EngineMemory(history)
        rulebook = EngineRulebook(library)
        verifier = RuleVerifier(history)
        return cls(
            perceiver=Perception(),
            history=history,
            library=library,
            memory=memory,
            rulebook=rulebook,
            inducer=RuleInducer(llm_client, library, verifier, event_sink=event_sink),
            planner=RuleFirstPlanner(rulebook, memory, llm_client=llm_client),
            base_path=base_path,
        )
