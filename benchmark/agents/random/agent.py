from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path
from typing import Any


SCENARIO_PATH = Path(__file__).with_name("scenario.json")


class RandomAgent:
    """Small action baseline that uses only advertised ordinary actions."""

    def __init__(self, scenario_path: str | Path = SCENARIO_PATH) -> None:
        self.scenario = json.loads(
            Path(scenario_path).read_text(encoding="utf-8")
        )

    def select_action(
        self,
        observation: dict[str, Any],
        rng: random.Random,
    ) -> str:
        available = [
            int(action)
            for action in observation.get("available_actions", [])
            if int(action) in {1, 2, 3, 4, 5}
        ]
        if not available:
            raise ValueError("Observation has no ordinary available actions")
        return f"ACTION{rng.choice(available)}"

    def run(
        self,
        manager: Any,
        *,
        delay_seconds: float = 0,
    ) -> dict[str, Any]:
        run = self._create_run(manager)
        self._play(manager, run, delay_seconds)
        return self._payload(run)

    def start(
        self,
        manager: Any,
        *,
        delay_seconds: float = 0.5,
    ) -> dict[str, Any]:
        run = self._create_run(manager)
        thread = threading.Thread(
            target=self._play_safely,
            args=(manager, run, delay_seconds),
            name=f"random-agent-{run.run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return self._payload(run)

    def _create_run(self, manager: Any) -> Any:
        selected = list(self.scenario["games"])
        return manager.create(
            capabilities=["rule_learning", "closeness"],
            sample_size=len(selected),
            seed=int(self.scenario["seed"]),
            selected_games=selected,
            representation={
                "rendered_image": False,
                "legend": False,
                "action_semantics": False,
            },
        )

    def _play(
        self,
        manager: Any,
        run: Any,
        delay_seconds: float,
    ) -> None:
        rng = random.Random(int(self.scenario["seed"]))
        for game_id in self.scenario["games"]:
            alias = run.aliases[str(game_id)]
            observation = manager.reset(
                run.run_id,
                run.token,
                game_alias=alias,
                guid=None,
            )
            for _ in range(int(self.scenario["actions_per_game"])):
                if delay_seconds:
                    time.sleep(delay_seconds)
                action = self.select_action(observation, rng)
                observation = manager.action(
                    run.token,
                    action=action,
                    game_alias=alias,
                    guid=str(observation["guid"]),
                )
                if alias in run.completed_aliases:
                    break
        manager.close(run.run_id, run.token)

    def _play_safely(
        self,
        manager: Any,
        run: Any,
        delay_seconds: float,
    ) -> None:
        try:
            self._play(manager, run, delay_seconds)
        except Exception as exc:
            run.status = "error"
            manager._append_event(
                run,
                {
                    "type": "agent_error",
                    "message": str(exc),
                },
            )

    def _payload(self, run: Any) -> dict[str, Any]:
        return {
            **run.public(),
            "run_token": run.token,
            "monitor_token": run.monitor_token,
            "simulation": {
                "scenario_id": self.scenario["scenario_id"],
                "fixture_warning": "Random action baseline.",
                "delay_seconds": self.scenario.get("delay_seconds", 0.5),
            },
            "result": run.result,
        }
