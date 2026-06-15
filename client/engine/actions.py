from __future__ import annotations

from dataclasses import dataclass

from client.engine.base_env import BaseEnv
from client.engine.planner import PlanDecision
from client.engine.state import EngineState
from client.engine.types import FrameData, GameAction


@dataclass(frozen=True)
class StepOutcome:
    """Result of executing one chosen action against the real environment."""

    before_frame: FrameData
    before_state: EngineState
    decision: PlanDecision
    after_frame: FrameData
    after_state: EngineState

    @property
    def action(self) -> GameAction:
        return self.decision.action


class ActionExecutor:
    """Executes planner decisions and returns comparable before/after state."""

    def __init__(self, env: BaseEnv, perceiver) -> None:
        self.env = env
        self.perceiver = perceiver

    def execute(
        self,
        before_frame: FrameData,
        before_state: EngineState,
        decision: PlanDecision,
    ) -> StepOutcome:
        after_frame = self.env.step(decision.action)
        after_state = self.perceiver.perceive(after_frame)
        return StepOutcome(
            before_frame=before_frame,
            before_state=before_state,
            decision=decision,
            after_frame=after_frame,
            after_state=after_state,
        )
