from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RunState:
    guid: str
    game_id: str
    session_id: str
    win_levels: int
    levels_completed: int = 0
    actions: int = 0
    resets: int = 0
    state: str = "NOT_FINISHED"


@dataclass
class EnvironmentState:
    game_id: str
    win_levels: int
    runs: list[RunState] = field(default_factory=list)


@dataclass
class ScorecardState:
    card_id: str
    tags: list[str] = field(default_factory=list)
    source_url: str | None = None
    opaque: dict[str, Any] | None = None
    open_at: str = field(default_factory=utc_now)
    last_update: str = field(default_factory=utc_now)
    published_at: str | None = None
    environments: dict[str, EnvironmentState] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        environments = []
        total_actions = 0
        total_levels = 0
        total_levels_completed = 0
        total_environments_completed = 0
        total_score = 0

        for environment in self.environments.values():
            env_actions = sum(run.actions for run in environment.runs)
            env_resets = sum(run.resets for run in environment.runs)
            env_levels_completed = max(
                (run.levels_completed for run in environment.runs), default=0
            )
            env_completed = any(run.state == "WIN" for run in environment.runs)
            total_actions += env_actions
            total_levels += environment.win_levels
            total_levels_completed += env_levels_completed
            total_environments_completed += int(env_completed)
            total_score += env_levels_completed

            environments.append(
                {
                    "id": environment.game_id,
                    "runs": [
                        {
                            "id": run.game_id,
                            "guid": run.guid,
                            "score": run.levels_completed,
                            "levels_completed": run.levels_completed,
                            "actions": run.actions,
                            "resets": run.resets,
                            "state": run.state,
                            "completed": run.state == "WIN",
                            "level_scores": [],
                            "level_actions": [],
                            "level_baseline_actions": [],
                            "number_of_levels": run.win_levels,
                            "number_of_environments": 1,
                        }
                        for run in environment.runs
                    ],
                    "score": env_levels_completed,
                    "actions": env_actions,
                    "levels_completed": env_levels_completed,
                    "completed": env_completed,
                    "level_count": environment.win_levels,
                    "resets": env_resets,
                }
            )

        summary = {
            "card_id": self.card_id,
            "score": total_score,
            "tags": self.tags,
            "environments": environments,
            "tags_scores": [],
            "open_at": self.open_at,
            "last_update": self.last_update,
            "total_environments_completed": total_environments_completed,
            "total_environments": len(self.environments),
            "total_levels_completed": total_levels_completed,
            "total_levels": total_levels,
            "total_actions": total_actions,
        }
        if self.source_url is not None:
            summary["source_url"] = self.source_url
        if self.opaque is not None:
            summary["opaque"] = self.opaque
        if self.published_at is not None:
            summary["published_at"] = self.published_at
        return summary


class ScorecardStore:
    def __init__(self) -> None:
        self._open: dict[str, ScorecardState] = {}
        self._closed: dict[str, ScorecardState] = {}
        self._guid_to_card: dict[str, str] = {}

    def open(
        self,
        tags: list[str] | None = None,
        source_url: str | None = None,
        opaque: dict[str, Any] | None = None,
    ) -> ScorecardState:
        card = ScorecardState(
            card_id=str(uuid4()), tags=tags or [], source_url=source_url, opaque=opaque
        )
        self._open[card.card_id] = card
        return card

    def get(self, card_id: str) -> ScorecardState:
        card = self._open.get(card_id) or self._closed.get(card_id)
        if not card:
            raise KeyError(card_id)
        return card

    def require_open(self, card_id: str) -> ScorecardState:
        card = self._open.get(card_id)
        if not card:
            raise KeyError(card_id)
        return card

    def require_open_for_guid(self, guid: str) -> ScorecardState:
        card_id = self._guid_to_card.get(guid)
        if card_id is None:
            raise KeyError(guid)
        return self.require_open(card_id)

    def close(self, card_id: str) -> ScorecardState:
        card = self._open.pop(card_id)
        card.last_update = utc_now()
        card.published_at = card.last_update
        self._closed[card.card_id] = card
        return card

    def register_run(
        self,
        card_id: str,
        guid: str,
        game_id: str,
        session_id: str,
        win_levels: int,
        levels_completed: int,
        state: str,
    ) -> None:
        card = self.require_open(card_id)
        environment = card.environments.setdefault(
            game_id, EnvironmentState(game_id=game_id, win_levels=win_levels)
        )
        environment.runs.append(
            RunState(
                guid=guid,
                game_id=game_id,
                session_id=session_id,
                win_levels=win_levels,
                levels_completed=levels_completed,
                state=state,
            )
        )
        card.last_update = utc_now()
        self._guid_to_card[guid] = card_id

    def update_run(
        self,
        guid: str,
        *,
        levels_completed: int,
        state: str,
        increment_actions: int = 0,
        increment_resets: int = 0,
    ) -> None:
        card_id = self._guid_to_card[guid]
        card = self.require_open(card_id)
        for environment in card.environments.values():
            for run in environment.runs:
                if run.guid == guid:
                    run.levels_completed = levels_completed
                    run.state = state
                    run.actions += increment_actions
                    run.resets += increment_resets
                    card.last_update = utc_now()
                    return
        raise KeyError(guid)
