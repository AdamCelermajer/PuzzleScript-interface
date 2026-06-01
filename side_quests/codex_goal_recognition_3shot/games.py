from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POOL_PATH = (
    ROOT
    / "deploy"
    / "railway-human-goal-study"
    / "dataset"
    / "excluded_games.json"
)


def load_curated_games(path: Path = DEFAULT_POOL_PATH) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    games = data.get("selection", {}).get("selected_games", [])
    if not isinstance(games, list):
        raise ValueError(f"Expected selected_games list in {path}")
    return [str(game).strip() for game in games if str(game).strip()]
