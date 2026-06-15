import time
from typing import Callable, Optional

from client.engine.actions import ActionExecutor
from client.engine.architecture import EngineArchitecture
from client.engine.base_env import BaseEnv
from client.engine.llm_client import Config, LlmClient
from client.engine.loop import RuleReasoningLoop
from client.engine.types import FrameData, GameAction


HistoryEntry = tuple[FrameData, GameAction, FrameData]


class Agent:
    """Compatibility container for the modular rule-reasoning runtime."""

    def __init__(
        self,
        config: Config,
        llm_client: LlmClient,
        event_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.cfg = config
        self.llm_client = llm_client
        self.event_sink = event_sink
        self.history: list[HistoryEntry] = []
        self.engine = EngineArchitecture.from_config(
            self.cfg, self.llm_client, event_sink=self.event_sink
        )


def _make_loop(
    env: BaseEnv,
    agent: Agent,
    *,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> RuleReasoningLoop:
    return RuleReasoningLoop(
        env,
        agent.engine.perceiver,
        agent.engine.memory,
        agent.engine.rulebook,
        agent.engine.planner,
        agent.engine.inducer,
        ActionExecutor(env, agent.engine.perceiver),
        dashboard=dashboard,
        event_sink=event_sink,
        sleep_fn=time.sleep,
    )


def run_learning_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    loop = _make_loop(env, agent, dashboard=dashboard, event_sink=event_sink)
    loop.run(max_steps=cfg.max_steps, game_id=cfg.game)
    agent.history = loop.history


def run_solving_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    loop = _make_loop(env, agent, dashboard=dashboard, event_sink=event_sink)
    loop.run(max_steps=cfg.max_steps, game_id=cfg.game)
    agent.history = loop.history
