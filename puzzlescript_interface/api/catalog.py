from dataclasses import dataclass
from pathlib import Path
import re


DEFAULT_GAME_VERSION = "v1"
MAX_VISIBLE_SYMBOLS = 15
PUBLIC_GAME_ID_RE = re.compile(r"^(ps_[a-z0-9_]+)-v(\d+)$")


@dataclass(frozen=True)
class GameCatalogEntry:
    game_id: str
    title: str
    source_name: str
    file_path: Path


def _public_game_stem(source_name: str) -> str:
    safe_name = re.sub(r"[^a-z0-9]+", "_", source_name.lower()).strip("_")
    return f"ps_{safe_name}"


def public_game_id(source_name: str, version: str = DEFAULT_GAME_VERSION) -> str:
    return f"{_public_game_stem(source_name)}-{version}"


def _display_title(game_id: str) -> str:
    match = PUBLIC_GAME_ID_RE.match(game_id)
    if not match:
        return game_id
    return match.group(1)[3:].replace("_", "-")


def _public_id_stem(game_id: str) -> str:
    match = PUBLIC_GAME_ID_RE.match(game_id)
    if not match:
        return game_id
    return match.group(1)


def _visible_symbol_count(file_path: Path) -> int:
    in_legend = False
    visible_symbols = 0
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "LEGEND":
            in_legend = True
            continue
        if in_legend and line == "COLLISIONLAYERS":
            break
        if in_legend and re.match(r"^[A-Za-z0-9.\-]\s*=\s*", line):
            visible_symbols += 1
    return visible_symbols


def build_catalog(games_dir: str | Path) -> list[GameCatalogEntry]:
    base_path = Path(games_dir)
    catalog: list[GameCatalogEntry] = []
    for file_path in sorted(base_path.glob("*/script.txt")):
        game_id = file_path.parent.name
        if _visible_symbol_count(file_path) > MAX_VISIBLE_SYMBOLS:
            continue
        catalog.append(
            GameCatalogEntry(
                game_id=game_id,
                title=_display_title(game_id),
                source_name=game_id,
                file_path=file_path,
            )
        )
    return catalog


def resolve_game_entry(
    catalog: list[GameCatalogEntry], lookup: str
) -> GameCatalogEntry:
    normalized_lookup = lookup.strip().lower()
    for entry in catalog:
        public_stem = _public_id_stem(entry.game_id)
        if normalized_lookup in {
            entry.game_id.lower(),
            public_stem.lower(),
            entry.title.lower(),
            entry.source_name.lower(),
        }:
            return entry
    raise KeyError(f"Unknown PuzzleScript game: {lookup}")
