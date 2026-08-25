from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any


SCENARIO_PATH = Path(__file__).with_name("scenario.json")
ACTION_IDS = {
    "UP": "ACTION1",
    "DOWN": "ACTION2",
    "LEFT": "ACTION3",
    "RIGHT": "ACTION4",
    "ACTION": "ACTION5",
}


class SimulatedPartialAgent:
    """Deterministic evaluator fixture that produces visibly partial scores.

    This is a dashboard/test fixture, not a fair benchmark submission. Its
    rule answers intentionally use saved evaluator artifacts to create a
    stable learning curve with known correct and incorrect predictions.
    """

    def __init__(self, scenario_path: str | Path = SCENARIO_PATH) -> None:
        self.scenario_path = Path(scenario_path)
        self.scenario = json.loads(
            self.scenario_path.read_text(encoding="utf-8")
        )
        self.challenge_number = 0

    def run(self, manager: Any) -> dict[str, Any]:
        run = self._create_run(manager)
        played = self._play(manager, run, delay_seconds=0)
        return self._payload(run, played)

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
            name=f"partial-agent-{run.run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return self._payload(run, [])

    def _create_run(self, manager: Any) -> Any:
        selected_games = [
            str(item["game_id"]) for item in self.scenario["games"]
        ]
        return manager.create(
            capabilities=["rule_learning", "closeness"],
            sample_size=len(selected_games),
            seed=int(self.scenario["seed"]),
            selected_games=selected_games,
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
        *,
        delay_seconds: float,
    ) -> list[dict[str, Any]]:
        played = []
        for game_plan in self.scenario["games"]:
            game_id = str(game_plan["game_id"])
            alias = run.aliases[game_id]
            observation = manager.reset(
                run.run_id,
                run.token,
                game_alias=alias,
                guid=None,
            )
            self._answer_if_present(manager, run, observation)
            game = next(
                item
                for item in run.games
                if str(item["game_id"]) == game_id
            )
            solution = list(game["reference"]["path"])
            fraction = float(game_plan["solution_fraction"])
            action_count = (
                len(solution)
                if fraction >= 1
                else max(1, int(round(len(solution) * fraction)))
            )
            action_count = min(action_count, len(solution))
            for action_name in solution[:action_count]:
                if delay_seconds:
                    time.sleep(delay_seconds)
                observation = manager.action(
                    run.token,
                    action=ACTION_IDS[action_name],
                    game_alias=alias,
                    guid=str(observation["guid"]),
                )
                self._answer_if_present(manager, run, observation)
            played.append(
                {
                    "game_id": game_id,
                    "alias": alias,
                    "solution_actions_played": action_count,
                    "solution_actions_total": len(solution),
                }
            )
        manager.close(run.run_id, run.token)
        return played

    def _play_safely(
        self,
        manager: Any,
        run: Any,
        delay_seconds: float,
    ) -> None:
        try:
            self._play(
                manager,
                run,
                delay_seconds=delay_seconds,
            )
        except Exception as exc:
            run.status = "error"
            manager._append_event(
                run,
                {
                    "type": "agent_error",
                    "message": str(exc),
                },
            )

    def _payload(
        self,
        run: Any,
        played: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **run.public(),
            "run_token": run.token,
            "monitor_token": run.monitor_token,
            "simulation": {
                "scenario_id": self.scenario["scenario_id"],
                "fixture_warning": (
                    "Deterministic dashboard fixture; not a fair agent result."
                ),
                "games": played,
            },
            "result": run.result,
        }

    def _answer_if_present(
        self,
        manager: Any,
        run: Any,
        observation: dict[str, Any],
    ) -> None:
        public = observation.get("benchmark_challenge")
        if not public:
            return
        challenge = next(
            item
            for item in run.rule_challenges
            if item["challenge_id"] == public["challenge_id"]
        )
        correct = self._correct_count(challenge)
        predictions = []
        for index, probe in enumerate(challenge["probes"]):
            predicted = (
                deepcopy(probe["expected_frame"])
                if index < correct
                else self._wrong_frame(probe["expected_frame"])
            )
            predictions.append(
                {
                    "probe_id": probe["probe_id"],
                    "predicted_frame": predicted,
                }
            )
        manager.submit_rule_predictions(
            run.run_id,
            run.token,
            challenge["challenge_id"],
            predictions,
        )
        self.challenge_number += 1

    def _correct_count(self, challenge: dict[str, Any]) -> int:
        initial = int(
            self.scenario["initial_correct_rule_predictions"]
        )
        if challenge["checkpoint"] == "level_start":
            return initial
        if challenge["checkpoint"] == "every_10_actions":
            return min(9, initial + int(challenge["action_number"]) // 10)
        if challenge["checkpoint"] == "level_complete":
            return 8
        return min(9, initial + self.challenge_number)

    @staticmethod
    def _wrong_frame(frame: list[list[int]]) -> list[list[int]]:
        wrong = deepcopy(frame)
        if not wrong or not wrong[0]:
            return [[1]]
        wrong[0][0] = (int(wrong[0][0]) + 1) % 16
        return wrong
