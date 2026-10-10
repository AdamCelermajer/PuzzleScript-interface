from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from client.arc.arcade_env import ArcadeEnv

from avo.core.framework import Observation, Transition
from avo.core.profile import TaskEvaluation
from avo.environments.puzzlescript.adapter import PuzzleScriptEnvironment


@dataclass(frozen=True)
class PuzzleScriptProfile:
    environment: PuzzleScriptEnvironment
    profile_id: str = "puzzlescript"
    objective: str = (
        "Build and validate a reusable autonomous solver that can win from a fresh reset "
        "without further Codex reasoning; manually chosen gameplay progress is only research."
    )

    def evaluate(
        self,
        history: Sequence[Transition],
        current: Observation,
    ) -> TaskEvaluation:
        progress = current.progress if isinstance(current.progress, Mapping) else {}
        levels_completed = int(progress.get("levels_completed", 0))
        win_levels = int(progress.get("win_levels", 0))
        success = current.status == "WIN"
        return TaskEvaluation(
            terminal=current.status in {"WIN", "GAME_OVER"},
            success=success,
            fitness=float(levels_completed),
            score={
                "success": int(success),
                "levels_completed": levels_completed,
                "win_levels": win_levels,
                "environment_actions": len(history),
            },
        )


def create_profile(settings: dict[str, Any]) -> PuzzleScriptProfile:
    from .adapter import _backend_call
    raw_environment = _backend_call("scorecard/open", lambda: ArcadeEnv(
        game_id=str(settings["game_id"]),
        backend_url=str(settings.get("backend_url", "http://localhost:8000")),
        api_key=str(settings.get("api_key", "")) or None,
    ))
    return PuzzleScriptProfile(PuzzleScriptEnvironment(raw_environment))
