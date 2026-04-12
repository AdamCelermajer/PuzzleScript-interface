from dataclasses import dataclass
from pathlib import Path


DEFAULT_VERSION = "v1"


@dataclass(frozen=True)
class GameCatalogEntry:
    game_id: str
    title: str
    source_name: str
    file_path: Path


def build_catalog(
    games_dir: str | Path, version: str = DEFAULT_VERSION
) -> list[GameCatalogEntry]:
    base_path = Path(games_dir)
    catalog: list[GameCatalogEntry] = []
    for file_path in sorted(base_path.glob("*.txt")):
        source_name = file_path.stem
        catalog.append(
            GameCatalogEntry(
                game_id=f"{source_name}-{version}",
                title=source_name,
                source_name=source_name,
                file_path=file_path,
            )
        )
    return catalog


def resolve_game_entry(
    catalog: list[GameCatalogEntry], lookup: str
) -> GameCatalogEntry:
    normalized_lookup = lookup.strip().lower()
    for entry in catalog:
        base_alias = entry.source_name.split("-", 1)[0].lower()
        if normalized_lookup in {
            entry.game_id.lower(),
            entry.title.lower(),
            entry.source_name.lower(),
            base_alias,
        }:
            return entry
    raise KeyError(f"Unknown PuzzleScript game: {lookup}")
