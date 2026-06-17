from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from client.engine.induction import RuleInducer
from client.engine.llm_client import Config
from client.engine.memory import EngineMemory
from client.engine.perception import Perception
from client.engine.planner import Planner
from client.engine.rulebook import Rulebook
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
    memory: EngineMemory
    rulebook: Rulebook
    inducer: RuleInducer
    planner: Planner
    base_path: Path

    @classmethod
    def from_config(
        cls, config: Config, llm_client, event_sink=None
    ) -> "EngineArchitecture":
        base_path = game_rules_path(config.rules_dir, config.game)
        memory = EngineMemory(base_path / "timeline.jsonl")
        rulebook = Rulebook(base_path)
        verifier = RuleVerifier(memory)
        return cls(
            perceiver=Perception(),
            memory=memory,
            rulebook=rulebook,
            inducer=RuleInducer(llm_client, rulebook, verifier, event_sink=event_sink),
            planner=Planner(rulebook=rulebook, memory=memory, llm_client=llm_client),
            base_path=base_path,
        )
