from __future__ import annotations

from client.engine.memory import EngineMemory
from client.engine.planner import Planner
from client.engine.rulebook import EngineRulebook


class RuleFirstPlanner(Planner):
    """Current reasoning policy: verified rules first, LLM exploratory plan second."""

    def __init__(
        self,
        rulebook: EngineRulebook,
        memory: EngineMemory,
        llm_client=None,
        max_depth: int = 20,
        node_limit: int = 200,
    ) -> None:
        super().__init__(
            rulebook.library,
            memory.history,
            llm_client=llm_client,
            max_depth=max_depth,
            node_limit=node_limit,
        )
