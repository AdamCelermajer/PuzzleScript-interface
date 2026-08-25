from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


GAMES_ROOT = Path(__file__).with_name("games")
TRACKS = {"rule_learning", "closeness"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object in {path}")
    return payload


def load_catalog(path: str | Path | None = None) -> dict[str, Any]:
    if path is not None:
        payload = _read_json(Path(path))
        if not {"catalog_id", "version", "games"} <= payload.keys():
            raise ValueError("Catalog needs catalog_id, version, and games")
        return payload

    index = _read_json(GAMES_ROOT / "index.json")
    games: list[dict[str, Any]] = []
    for entry in index.get("games", []):
        game_root = GAMES_ROOT / str(entry["directory"])
        game = _read_json(game_root / "game.json")
        levels: list[dict[str, Any]] = []
        for level in game.get("level_artifacts", []):
            level_root = game_root / str(level["directory"])
            solution = _read_json(level_root / "solution.json")
            probes = _read_json(level_root / "rule-probes.json")
            closeness = _read_json(level_root / "closeness.json")
            levels.append(
                {
                    **level,
                    "solution": solution,
                    "rule_probes_artifact": probes,
                    "closeness_artifact": closeness,
                }
            )
        if not levels:
            continue
        primary = levels[0]
        games.append(
            {
                "game_id": game["game_id"],
                "max_actions": int(game["max_actions"]),
                "artifact_status": game["artifact_status"],
                "artifact_directory": str(game_root),
                "tracks": {
                    "rule_learning": {
                        "enabled": (
                            len(
                                primary["rule_probes_artifact"].get(
                                    "probes", []
                                )
                            )
                            == int(
                                primary["rule_probes_artifact"].get(
                                    "requested_probes", 10
                                )
                            )
                        )
                    },
                    "closeness": {
                        "enabled": bool(
                            primary["closeness_artifact"].get(
                                "replay_verified"
                            )
                        )
                    },
                },
                "levels": levels,
                "reference": {
                    "scope": "artifact_level",
                    "level_index": int(primary["level_index"]),
                    "actions": int(primary["solution_actions"]),
                    "path": primary["solution"]["actions"],
                    "replay_verified": bool(primary["replay_verified"]),
                },
            }
        )
    if not games:
        raise ValueError("Benchmark games folder contains no usable artifacts")
    return {
        "catalog_id": index["benchmark_id"],
        "version": index["version"],
        "source": {
            "scope_note": (
                "Per-game, per-level replay-verified artifacts. Closeness is "
                "exact only when the observed frame matches a saved solution "
                "trace state."
            ),
            "games_root": str(GAMES_ROOT),
        },
        "games": games,
    }


def sample_games(
    catalog: dict[str, Any],
    *,
    track: str,
    sample_size: int | None,
    seed: int,
    selected_games: list[str] | None = None,
) -> list[dict[str, Any]]:
    return sample_games_for_capabilities(
        catalog,
        capabilities=[track],
        sample_size=sample_size,
        seed=seed,
        selected_games=selected_games,
    )


def sample_games_for_capabilities(
    catalog: dict[str, Any],
    *,
    capabilities: list[str],
    sample_size: int | None,
    seed: int,
    selected_games: list[str] | None = None,
) -> list[dict[str, Any]]:
    unknown = set(capabilities) - TRACKS
    if unknown:
        raise ValueError(
            f"Unknown benchmark capabilities: {', '.join(sorted(unknown))}"
        )
    if not capabilities:
        raise ValueError("Select at least one benchmark capability")
    eligible = [
        game
        for game in catalog["games"]
        if all(
            game.get("tracks", {}).get(capability, {}).get("enabled") is True
            for capability in capabilities
        )
    ]
    if selected_games:
        wanted = set(selected_games)
        available = {str(game["game_id"]) for game in eligible}
        missing = wanted - available
        if missing:
            raise ValueError(
                "Games unavailable for the selected capabilities: "
                f"{', '.join(sorted(missing))}"
            )
        eligible = [
            game for game in eligible if str(game["game_id"]) in wanted
        ]
    rng = random.Random(seed)
    rng.shuffle(eligible)
    if sample_size is None:
        return eligible
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    if sample_size > len(eligible):
        raise ValueError(
            f"Requested {sample_size} games but only {len(eligible)} support "
            "all selected capabilities"
        )
    return eligible[:sample_size]
