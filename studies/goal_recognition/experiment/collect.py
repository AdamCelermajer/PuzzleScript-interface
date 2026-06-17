from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any

from client.arc.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid


@dataclass
class TrajectoryResult:
    evidence_mode: str
    trajectory: list[dict[str, Any]]
    actions_taken: list[str]
    available_actions: list[str]
    state: str
    levels_completed: int
    win_levels: int
    guid: str
    projection: dict[str, Any]


def choose_random_action(
    frame_data: FrameData,
    rng: random.Random,
) -> GameAction | None:
    controls = {GameAction.RESET, GameAction.ACTION7}
    actions = [
        action
        for action in frame_data.available_actions
        if action not in controls
    ]
    if not actions:
        return None
    return rng.choice(actions)


def random_action_data(
    action: GameAction,
    frame_data: FrameData,
    rng: random.Random,
) -> dict[str, int] | None:
    if action != GameAction.ACTION6:
        return None

    grid = last_grid(frame_data.frame)
    height = len(grid)
    width = len(grid[0]) if height else 0
    if width <= 0 or height <= 0:
        return None
    return {"x": rng.randrange(width), "y": rng.randrange(height)}


def action_label(action: GameAction, data: dict[str, int] | None) -> str:
    if not data:
        return action.name
    return f"{action.name} {json.dumps(data, sort_keys=True)}"


def collect_random_trajectory(
    env: Any,
    rng: random.Random,
    *,
    steps: int = 3,
    evidence_mode: str | None = None,
) -> TrajectoryResult:
    frame_data = env.reset()
    trajectory = [{"action": GameAction.RESET.name, "grid": last_grid(frame_data.frame)}]
    actions_taken: list[str] = []

    for _ in range(steps):
        if frame_data.state in {GameState.WIN, GameState.GAME_OVER}:
            break

        action = choose_random_action(frame_data, rng)
        if action is None:
            break

        data = random_action_data(action, frame_data, rng)
        label = action_label(action, data)
        actions_taken.append(label)
        frame_data = env.step(action, data=data)
        trajectory.append({"action": label, "grid": last_grid(frame_data.frame)})

    return TrajectoryResult(
        evidence_mode=evidence_mode or ("one_frame" if steps == 0 else "three_random_actions"),
        trajectory=trajectory,
        actions_taken=actions_taken,
        available_actions=[action.name for action in frame_data.available_actions],
        state=frame_data.state.name,
        levels_completed=frame_data.levels_completed,
        win_levels=frame_data.win_levels,
        guid=frame_data.guid,
        projection=frame_data.projection,
    )


def collect_three_shot_trajectory(
    env: Any,
    rng: random.Random,
    *,
    steps: int = 3,
) -> TrajectoryResult:
    return collect_random_trajectory(
        env,
        rng,
        steps=steps,
        evidence_mode="three_random_actions",
    )
