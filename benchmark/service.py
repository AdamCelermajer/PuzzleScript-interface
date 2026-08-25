from __future__ import annotations

import json
import os
import secrets
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from benchmark.catalog import load_catalog, sample_games_for_capabilities
from benchmark.tracks import (
    aggregate_closeness,
    score_frame_closeness,
    score_rule_predictions,
)


RESULTS_DIR = Path(__file__).with_name("results")
CAPABILITIES = {"rule_learning", "closeness"}
ACTION_SEMANTICS = {
    "ACTION1": "Up",
    "ACTION2": "Down",
    "ACTION3": "Left",
    "ACTION4": "Right",
    "ACTION5": "Action",
    "ACTION7": "Undo",
}
STANDARD_FRAME_FIELDS = {
    "game_id",
    "guid",
    "frame",
    "state",
    "levels_completed",
    "win_levels",
    "action_input",
    "available_actions",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _last_frame(payload: dict[str, Any]) -> list[list[int]]:
    frames = payload.get("frame") or []
    if not frames:
        return []
    return deepcopy(frames[-1])


def _arc_state(value: Any) -> str:
    state = str(value or "").upper()
    if state in {"WIN", "GAME_OVER"}:
        return state
    return "NOT_FINISHED"


class UpstreamArcClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 45,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            json=payload,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(
                f"Upstream ARC response from {path} was not an object"
            )
        return data


def normalize_representation(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    rendered = bool(value.get("rendered_image", False))
    legend = bool(value.get("legend", False))
    return {
        "arc_grid_provided": True,
        "rendered_image_provided": rendered,
        "legend_provided": legend,
        "legend_origin": "benchmark_ground_truth" if legend else "none",
        "action_semantics_provided": bool(
            value.get("action_semantics", False)
        ),
    }


@dataclass
class BenchmarkRun:
    run_id: str
    token: str
    monitor_token: str
    capabilities: list[str]
    seed: int
    games: list[dict[str, Any]]
    aliases: dict[str, str]
    representation: dict[str, Any]
    upstream_card_id: str
    status: str = "ready"
    created_at: str = field(default_factory=utc_now)
    closed_at: str | None = None
    guid_to_alias: dict[str, str] = field(default_factory=dict)
    actions_by_alias: dict[str, int] = field(default_factory=dict)
    current_observations: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    completed_aliases: set[str] = field(default_factory=set)
    events: list[dict[str, Any]] = field(default_factory=list)
    rule_challenges: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None

    @property
    def reverse_aliases(self) -> dict[str, str]:
        return {alias: game_id for game_id, alias in self.aliases.items()}

    def public(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "capabilities": self.capabilities,
            "status": self.status,
            "seed": self.seed,
            "scorecard_id": self.run_id,
            "game_ids": [
                self.aliases[str(game["game_id"])] for game in self.games
            ],
            "action_budgets": {
                self.aliases[str(game["game_id"])]: int(game["max_actions"])
                for game in self.games
            },
            "representation": self.representation,
            "created_at": self.created_at,
            "closed_at": self.closed_at,
            "result": self.result,
        }


class BenchmarkRunManager:
    def __init__(
        self,
        *,
        catalog: dict[str, Any] | None = None,
        upstream: UpstreamArcClient | None = None,
        results_dir: str | Path = RESULTS_DIR,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.upstream = upstream or UpstreamArcClient(
            os.getenv("BENCHMARK_ARC_URL", "http://127.0.0.1:8000")
        )
        self.results_dir = Path(results_dir)
        self._runs: dict[str, BenchmarkRun] = {}
        self._token_to_run: dict[str, str] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        capabilities: list[str],
        sample_size: int | None,
        seed: int,
        selected_games: list[str] | None,
        representation: dict[str, Any] | None,
    ) -> BenchmarkRun:
        capabilities = list(dict.fromkeys(capabilities))
        games = sample_games_for_capabilities(
            self.catalog,
            capabilities=capabilities,
            sample_size=sample_size,
            seed=seed,
            selected_games=selected_games,
        )
        alias_values = [
            f"env-{index:04d}" for index in range(1, len(games) + 1)
        ]
        secrets.SystemRandom().shuffle(alias_values)
        aliases = {
            str(game["game_id"]): alias
            for game, alias in zip(games, alias_values)
        }
        run_id = str(uuid4())
        card = self.upstream.request(
            "POST",
            "/api/scorecard/open",
            {
                "tags": [
                    "benchmark",
                    self.catalog["catalog_id"],
                    *capabilities,
                ],
                "opaque": {"benchmark_run_id": run_id},
            },
        )
        run = BenchmarkRun(
            run_id=run_id,
            token=str(uuid4()),
            monitor_token=str(uuid4()),
            capabilities=capabilities,
            seed=seed,
            games=deepcopy(games),
            aliases=aliases,
            representation=normalize_representation(representation),
            upstream_card_id=str(card["card_id"]),
        )
        with self._lock:
            self._runs[run.run_id] = run
            self._token_to_run[run.token] = run.run_id
        return run

    def get(self, run_id: str) -> BenchmarkRun:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            return self._runs[run_id]

    def from_token(self, token: str) -> BenchmarkRun:
        with self._lock:
            run_id = self._token_to_run.get(token)
        if not run_id:
            raise PermissionError("Invalid benchmark run token")
        return self.get(run_id)

    def require(self, run_id: str, token: str) -> BenchmarkRun:
        run = self.get(run_id)
        if not token or not secrets.compare_digest(token, run.token):
            raise PermissionError("Invalid benchmark run token")
        return run

    def require_monitor(self, run_id: str, monitor_token: str) -> BenchmarkRun:
        run = self.get(run_id)
        if not monitor_token or not secrets.compare_digest(
            monitor_token, run.monitor_token
        ):
            raise PermissionError("Invalid benchmark monitor token")
        return run

    def reset(
        self,
        run_id: str,
        token: str,
        *,
        game_alias: str,
        guid: str | None,
    ) -> dict[str, Any]:
        run = self.require(run_id, token)
        self._require_open(run)
        actual = run.reverse_aliases.get(game_alias)
        if not actual:
            raise KeyError(game_alias)
        game = self._game(run, game_alias)
        payload: dict[str, Any] = {
            "card_id": run.upstream_card_id,
            "game_id": actual,
            "level_index": int(game["reference"]["level_index"]),
        }
        if guid:
            payload["guid"] = guid
        response = self.upstream.request("POST", "/api/cmd/RESET", payload)
        response_guid = str(response["guid"])
        run.guid_to_alias[response_guid] = game_alias
        run.actions_by_alias[game_alias] = 0
        run.completed_aliases.discard(game_alias)
        run.current_observations[game_alias] = deepcopy(response)
        run.status = "running"
        challenge = self._create_rule_challenge(
            run, game_alias, checkpoint="level_start"
        )
        self._append_event(
            run,
            {
                "type": "reset",
                "game_alias": game_alias,
                "game_id": actual,
                "challenge_id": (
                    challenge["challenge_id"] if challenge else None
                ),
                "observation": self._monitor_observation(
                    response, game_alias
                ),
            },
        )
        return self._filter_observation(
            run, response, game_alias, challenge=challenge
        )

    def action(
        self,
        token: str,
        *,
        action: str,
        game_alias: str,
        guid: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run = self.from_token(token)
        self._require_open(run)
        if run.guid_to_alias.get(guid) != game_alias:
            raise ValueError("guid and game alias do not belong together")
        actual = run.reverse_aliases.get(game_alias)
        if not actual:
            raise KeyError(game_alias)
        before = run.current_observations.get(game_alias)
        if before is None:
            raise ValueError("RESET the environment before submitting actions")
        game = self._game(run, game_alias)
        actions_used = run.actions_by_alias.get(game_alias, 0)
        budget = int(game["max_actions"])
        if actions_used >= budget:
            raise ValueError(
                f"Action budget exhausted for {game_alias}: {budget}"
            )

        payload = {"game_id": actual, "guid": guid}
        if data:
            payload.update(data)
        response = self.upstream.request(
            "POST", f"/api/cmd/{action}", payload
        )
        action_number = actions_used + 1
        run.actions_by_alias[game_alias] = action_number
        run.current_observations[game_alias] = deepcopy(response)

        before_levels = int(before.get("levels_completed") or 0)
        after_levels = int(response.get("levels_completed") or before_levels)
        completed_level = (
            after_levels > before_levels
            or _arc_state(response.get("state")) == "WIN"
        )
        if completed_level:
            run.completed_aliases.add(game_alias)

        checkpoint: str | None = None
        if completed_level:
            checkpoint = "level_complete"
        elif action_number >= budget:
            checkpoint = "budget_end"
        elif action_number % 10 == 0:
            checkpoint = "every_10_actions"
        challenge = (
            self._create_rule_challenge(run, game_alias, checkpoint=checkpoint)
            if checkpoint
            else None
        )
        closeness = self._closeness_for(run, game_alias)
        self._append_event(
            run,
            {
                "type": "action",
                "game_alias": game_alias,
                "game_id": actual,
                "action": action,
                "action_number": action_number,
                "completed_level": completed_level,
                "closeness": closeness,
                "challenge_id": (
                    challenge["challenge_id"] if challenge else None
                ),
                "observation": self._monitor_observation(
                    response, game_alias
                ),
            },
        )
        return self._filter_observation(
            run, response, game_alias, challenge=challenge
        )

    def submit_rule_predictions(
        self,
        run_id: str,
        token: str,
        challenge_id: str,
        predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        run = self.require(run_id, token)
        self._require_open(run)
        challenge = next(
            (
                item
                for item in run.rule_challenges
                if item["challenge_id"] == challenge_id
            ),
            None,
        )
        if challenge is None:
            raise KeyError(challenge_id)
        if challenge["submitted"]:
            raise ValueError("Rule challenge has already been submitted")
        allowed_ids = {
            str(probe["probe_id"]) for probe in challenge["probes"]
        }
        supplied_ids = {
            str(prediction.get("probe_id")) for prediction in predictions
        }
        unknown = supplied_ids - allowed_ids
        if unknown:
            raise ValueError(
                f"Predictions contain unknown probe ids: "
                f"{', '.join(sorted(unknown))}"
            )
        score = score_rule_predictions(
            challenge["probes"], deepcopy(predictions)
        )
        challenge["predictions"] = deepcopy(predictions)
        challenge["submitted"] = True
        challenge["submitted_at"] = utc_now()
        challenge["score"] = score
        self._append_event(
            run,
            {
                "type": "rule_challenge_scored",
                "game_alias": challenge["game_alias"],
                "game_id": challenge["game_id"],
                "challenge_id": challenge_id,
                "checkpoint": challenge["checkpoint"],
                "score": deepcopy(score["summary"]),
            },
        )
        return {
            "challenge_id": challenge_id,
            "checkpoint": challenge["checkpoint"],
            "submitted": True,
            "score": score,
        }

    def scorecard(self, run_id: str, token: str) -> dict[str, Any]:
        run = self.require(run_id, token)
        if run.result is not None:
            return run.result
        return self._result_envelope(
            run, self._scores(run), reveal_identities=False
        )

    def monitor(
        self,
        run_id: str,
        monitor_token: str,
    ) -> dict[str, Any]:
        run = self.require_monitor(run_id, monitor_token)
        scores = (
            run.result["scores"]
            if run.result is not None
            else self._scores(run)
        )
        environments = []
        for game in run.games:
            game_id = str(game["game_id"])
            alias = run.aliases[game_id]
            observation = run.current_observations.get(alias)
            environments.append(
                {
                    "alias": alias,
                    "game_id": game_id,
                    "artifact_level": int(
                        game["reference"]["level_index"]
                    ),
                    "solution_actions": int(
                        game["reference"]["actions"]
                    ),
                    "rule_probe_count": len(
                        self._level(game)["rule_probes_artifact"].get(
                            "probes", []
                        )
                    ),
                    "action_budget": int(game["max_actions"]),
                    "actions_used": run.actions_by_alias.get(alias, 0),
                    "completed": alias in run.completed_aliases,
                    "closeness": self._closeness_for(run, alias),
                    "latest_rule_challenge": self._latest_challenge_public(
                        run, alias
                    ),
                    "observation": (
                        self._monitor_observation(observation, alias)
                        if observation
                        else None
                    ),
                }
            )
        return {
            "run_id": run.run_id,
            "status": run.status,
            "capabilities": run.capabilities,
            "seed": run.seed,
            "representation": run.representation,
            "created_at": run.created_at,
            "closed_at": run.closed_at,
            "environments": environments,
            "scores": scores,
            "rule_challenges": [
                self._challenge_monitor(item)
                for item in run.rule_challenges
            ],
            "events": deepcopy(run.events[-200:]),
        }

    def close(self, run_id: str, token: str) -> dict[str, Any]:
        run = self.require(run_id, token)
        if run.closed_at:
            return run.result or run.public()
        run.closed_at = utc_now()
        self.upstream.request(
            "POST",
            "/api/scorecard/close",
            {"card_id": run.upstream_card_id},
        )
        run.result = self._result_envelope(run, self._scores(run))
        run.status = "closed"
        self._append_event(
            run,
            {
                "type": "run_closed",
                "scores": deepcopy(run.result["scores"]),
            },
        )
        self._persist(run)
        return run.result

    def artifact_summary(self) -> dict[str, Any]:
        games = []
        for game in self.catalog["games"]:
            level = self._level(game)
            probes = level["rule_probes_artifact"]
            closeness = level["closeness_artifact"]
            games.append(
                {
                    "game_id": game["game_id"],
                    "artifact_status": game["artifact_status"],
                    "levels": len(game["levels"]),
                    "artifact_level": int(level["level_index"]),
                    "solution_actions": int(
                        level["solution"]["action_count"]
                    ),
                    "replay_verified": bool(level["replay_verified"]),
                    "rule_probes": len(probes.get("probes", [])),
                    "requested_rule_probes": int(
                        probes.get("requested_probes", 10)
                    ),
                    "rule_families": len(
                        probes.get("covered_rule_families", [])
                    ),
                    "rule_probe_levels": list(
                        probes.get("coverage_levels", [])
                    ),
                    "closeness_mode": closeness.get("mode"),
                    "closeness_trace_states": len(
                        closeness.get("trace", [])
                    ),
                }
            )
        return {
            "benchmark_id": self.catalog["catalog_id"],
            "version": self.catalog["version"],
            "games_root": self.catalog["source"].get("games_root"),
            "scope_note": self.catalog["source"]["scope_note"],
            "summary": {
                "games": len(games),
                "replay_verified": sum(
                    game["replay_verified"] for game in games
                ),
                "rule_probes": sum(game["rule_probes"] for game in games),
                "rule_ready_games": sum(
                    game["rule_probes"] == game["requested_rule_probes"]
                    for game in games
                ),
                "closeness_ready_games": sum(
                    bool(game["closeness_trace_states"]) for game in games
                ),
            },
            "games": games,
        }

    def _scores(self, run: BenchmarkRun) -> dict[str, Any]:
        scores: dict[str, Any] = {}
        if "rule_learning" in run.capabilities:
            scores["rule_learning"] = self._rule_learning_score(run)
        if "closeness" in run.capabilities:
            rows = [
                {
                    "alias": run.aliases[str(game["game_id"])],
                    "game_id": game["game_id"],
                    "level_index": int(
                        game["reference"]["level_index"]
                    ),
                    "closeness": self._closeness_for(
                        run, run.aliases[str(game["game_id"])]
                    ),
                }
                for game in run.games
            ]
            score = aggregate_closeness(rows)
            score["status"] = (
                "active"
                if run.current_observations
                else "awaiting_reset"
            )
            scores["closeness"] = score
        return scores

    def _rule_learning_score(self, run: BenchmarkRun) -> dict[str, Any]:
        submitted = [
            challenge
            for challenge in run.rule_challenges
            if challenge["submitted"]
        ]
        curves = []
        for challenge in run.rule_challenges:
            summary = (
                challenge["score"]["summary"]
                if challenge["submitted"]
                else {
                    "exact_frame": 0.0,
                    "cell_accuracy": 0.0,
                    "transition_edit_f1": 0.0,
                    "coverage": 0.0,
                }
            )
            curves.append(
                {
                    "challenge_id": challenge["challenge_id"],
                    "game_alias": challenge["game_alias"],
                    "checkpoint": challenge["checkpoint"],
                    "action_number": challenge["action_number"],
                    "submitted": challenge["submitted"],
                    "exact_frame": summary["exact_frame"],
                    "cell_accuracy": summary["cell_accuracy"],
                    "transition_edit_f1": summary[
                        "transition_edit_f1"
                    ],
                    "coverage": summary["coverage"],
                }
            )
        latest_by_alias: dict[str, dict[str, Any]] = {}
        for item in curves:
            latest_by_alias[item["game_alias"]] = item
        latest = list(latest_by_alias.values())
        metrics = (
            "exact_frame",
            "cell_accuracy",
            "transition_edit_f1",
            "coverage",
        )
        total_games = len(run.games)
        summary = {
            f"latest_{metric}": (
                round(
                    sum(item[metric] for item in latest) / total_games, 6
                )
                if total_games
                else None
            )
            for metric in metrics
        }
        summary.update(
            {
                "challenges_created": len(run.rule_challenges),
                "challenges_submitted": len(submitted),
                "games_challenged": len(latest),
                "games_tested": len(
                    {item["game_alias"] for item in submitted}
                ),
                "total_games": total_games,
            }
        )
        return {
            "track": "rule_learning",
            "mode": "periodic_hidden_transition_challenges",
            "primary_metric": "latest_macro_exact_frame_accuracy",
            "status": (
                "active"
                if run.rule_challenges
                else "awaiting_challenge"
            ),
            "summary": summary,
            "learning_curve": curves,
            "latest_by_game": latest,
        }

    def _closeness_for(
        self, run: BenchmarkRun, game_alias: str
    ) -> dict[str, Any]:
        observation = run.current_observations.get(game_alias)
        if observation is None:
            return {
                "available": False,
                "closeness": None,
                "percent": None,
                "remaining_actions": None,
                "basis": "level_not_started",
            }
        game = self._game(run, game_alias)
        return score_frame_closeness(
            self._level(game)["closeness_artifact"],
            _last_frame(observation),
            completed=game_alias in run.completed_aliases,
        )

    def _create_rule_challenge(
        self,
        run: BenchmarkRun,
        game_alias: str,
        *,
        checkpoint: str,
        deduplicate: bool = False,
    ) -> dict[str, Any] | None:
        if "rule_learning" not in run.capabilities:
            return None
        action_number = run.actions_by_alias.get(game_alias, 0)
        if deduplicate and any(
            item["game_alias"] == game_alias
            and item["checkpoint"] == checkpoint
            and item["action_number"] == action_number
            for item in run.rule_challenges
        ):
            return None
        game = self._game(run, game_alias)
        artifact_probes = self._level(game)[
            "rule_probes_artifact"
        ].get("probes", [])
        if not artifact_probes:
            return None
        challenge_id = f"challenge-{len(run.rule_challenges) + 1:06d}"
        probes = []
        for artifact_probe in artifact_probes:
            probe = deepcopy(artifact_probe)
            probe["probe_id"] = (
                f"{challenge_id}:{artifact_probe['probe_id']}"
            )
            probe["game_alias"] = game_alias
            probes.append(probe)
        challenge = {
            "challenge_id": challenge_id,
            "run_id": run.run_id,
            "game_alias": game_alias,
            "game_id": game["game_id"],
            "level_index": int(self._level(game)["level_index"]),
            "checkpoint": checkpoint,
            "action_number": action_number,
            "created_at": utc_now(),
            "probes": probes,
            "predictions": [],
            "submitted": False,
            "submitted_at": None,
            "score": None,
        }
        run.rule_challenges.append(challenge)
        self._append_event(
            run,
            {
                "type": "rule_challenge_created",
                "game_alias": game_alias,
                "game_id": game["game_id"],
                "challenge_id": challenge_id,
                "checkpoint": checkpoint,
                "action_number": action_number,
                "probe_count": len(probes),
            },
        )
        return challenge

    @staticmethod
    def _challenge_agent(challenge: dict[str, Any]) -> dict[str, Any]:
        return {
            "challenge_id": challenge["challenge_id"],
            "checkpoint": challenge["checkpoint"],
            "action_number": challenge["action_number"],
            "level_index": challenge["level_index"],
            "instructions": (
                "For each hidden transition, predict f2 from f1 and action. "
                "Submit a predicted_frame for every probe."
            ),
            "submit_path": (
                f"/api/benchmark/runs/{challenge['run_id']}/rule-challenges/"
                f"{challenge['challenge_id']}"
            ),
            "probes": [
                {
                    "probe_id": probe["probe_id"],
                    "before_frame": deepcopy(probe["before_frame"]),
                    "action": probe["action"],
                }
                for probe in challenge["probes"]
            ],
        }

    def _challenge_monitor(
        self, challenge: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            **self._challenge_agent(challenge),
            "game_alias": challenge["game_alias"],
            "game_id": challenge["game_id"],
            "created_at": challenge["created_at"],
            "submitted": challenge["submitted"],
            "submitted_at": challenge["submitted_at"],
            "score": deepcopy(challenge["score"]),
        }

    def _latest_challenge_public(
        self, run: BenchmarkRun, alias: str
    ) -> dict[str, Any] | None:
        challenge = next(
            (
                item
                for item in reversed(run.rule_challenges)
                if item["game_alias"] == alias
            ),
            None,
        )
        return (
            self._challenge_monitor(challenge) if challenge else None
        )

    def _filter_observation(
        self,
        run: BenchmarkRun,
        response: dict[str, Any],
        alias: str,
        *,
        challenge: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        filtered = {
            key: deepcopy(response[key])
            for key in STANDARD_FRAME_FIELDS
            if key in response
        }
        filtered["game_id"] = alias
        if run.representation["rendered_image_provided"] and response.get(
            "rendered_frame"
        ):
            filtered["rendered_frame"] = deepcopy(response["rendered_frame"])
        if run.representation["legend_provided"] and response.get("legend"):
            filtered["legend"] = deepcopy(response["legend"])
        if run.representation["action_semantics_provided"]:
            available = filtered.get("available_actions") or []
            filtered["action_semantics"] = {
                f"ACTION{action}": ACTION_SEMANTICS[f"ACTION{action}"]
                for action in available
                if f"ACTION{action}" in ACTION_SEMANTICS
            }
        if challenge is not None:
            filtered["benchmark_challenge"] = self._challenge_agent(challenge)
        return filtered

    @staticmethod
    def _monitor_observation(
        response: dict[str, Any],
        alias: str,
    ) -> dict[str, Any]:
        observation = {
            key: deepcopy(response[key])
            for key in STANDARD_FRAME_FIELDS
            if key in response
        }
        observation["game_id"] = alias
        if response.get("rendered_frame"):
            observation["rendered_frame"] = deepcopy(
                response["rendered_frame"]
            )
        if response.get("legend"):
            observation["legend"] = deepcopy(response["legend"])
        return observation

    @staticmethod
    def _append_event(
        run: BenchmarkRun,
        event: dict[str, Any],
    ) -> None:
        event.setdefault("event_id", f"event-{len(run.events) + 1:06d}")
        event["timestamp"] = utc_now()
        run.events.append(event)

    def _result_envelope(
        self,
        run: BenchmarkRun,
        scores: dict[str, Any],
        *,
        reveal_identities: bool = True,
    ) -> dict[str, Any]:
        visible_scores = deepcopy(scores)
        if not reveal_identities:
            for score in visible_scores.values():
                for row in score.get("games", []):
                    row.pop("game_id", None)
        games = []
        for game in run.games:
            item: dict[str, Any] = {
                "alias": run.aliases[str(game["game_id"])]
            }
            if reveal_identities:
                item.update(
                    {
                        "game_id": game["game_id"],
                        "artifact_level": int(
                            game["reference"]["level_index"]
                        ),
                        "solution_actions": int(
                            game["reference"]["actions"]
                        ),
                        "replay_verified": bool(
                            game["reference"]["replay_verified"]
                        ),
                    }
                )
            games.append(item)
        return {
            "benchmark_id": self.catalog["catalog_id"],
            "benchmark_version": self.catalog["version"],
            "run_id": run.run_id,
            "capabilities": run.capabilities,
            "seed": run.seed,
            "representation": run.representation,
            "reference_scope": self.catalog["source"]["scope_note"],
            "games": games,
            "scores": visible_scores,
            "created_at": run.created_at,
            "closed_at": run.closed_at,
        }

    def _persist(self, run: BenchmarkRun) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / f"{run.run_id}.json"
        path.write_text(
            json.dumps(run.result, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _level(game: dict[str, Any]) -> dict[str, Any]:
        return game["levels"][0]

    @staticmethod
    def _game(
        run: BenchmarkRun, game_alias: str
    ) -> dict[str, Any]:
        actual = run.reverse_aliases.get(game_alias)
        if not actual:
            raise KeyError(game_alias)
        return next(
            game
            for game in run.games
            if str(game["game_id"]) == actual
        )

    @staticmethod
    def _require_open(run: BenchmarkRun) -> None:
        if run.closed_at:
            raise ValueError("Benchmark run is already closed")
